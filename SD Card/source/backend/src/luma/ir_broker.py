"""Unprivileged, socket-activated USB IR broker with killable one-shot workers.

Only the local luma UID can submit a request. Application-level owner/privacy,
learned-button semantics and scene permission checks belong above this boundary.
No network listeners, shell, arbitrary paths, retries or stored recordings.
"""
import asyncio
from contextlib import suppress
import os
import socket
import struct
import sys
from time import monotonic

from .ir_linux import validate_request
from .ir_protocol import (MAX_WIRE, InfraredBusy, InfraredError, InfraredUnavailable,
                          decode, encode, send_result, validate_result)

SOCKET = '/run/luma-ir.sock'
DEADLINES = {'discover': 4, 'learn': 12, 'send': 4}


class Worker:
    def __init__(self, spawn=asyncio.create_subprocess_exec):
        self.spawn = spawn
        self.poisoned = False
        self.pending = set()

    def retain(self, task):
        self.pending.add(task)
        def finished(done):
            self.pending.discard(done)
            if not done.cancelled():
                with suppress(Exception): done.result()
        task.add_done_callback(finished)

    async def reap(self, process):
        if process.returncode is None:
            with suppress(ProcessLookupError): process.kill()
        waiter = asyncio.create_task(process.wait())
        done, _ = await asyncio.wait({waiter}, timeout=2)
        if not done:
            # A stuck kernel driver can keep a killed process unreaped. Do not
            # permit another operation to race it; administrator restart required.
            self.poisoned = True
            self.retain(waiter)
        else:
            waiter.result()

    def late_spawn(self, task):
        if task.cancelled(): return
        try: process = task.result()
        except Exception: return
        self.retain(asyncio.create_task(self.reap(process)))

    async def run(self, request):
        request = validate_request(request)
        if self.poisoned: raise InfraredUnavailable('Infrared service needs an administrator restart.')
        process = None
        # Isolated Python ignores PYTHONPATH/user site; installed module and venv
        # must be root-owned. Input goes through stdin, never argv or environment.
        spawning = asyncio.create_task(self.spawn(
            sys.executable, '-I', '-m', 'luma.ir_linux',
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, limit=MAX_WIRE + 1,
            env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': '/nonexistent'}))
        try:
            process = await asyncio.wait_for(asyncio.shield(spawning), 3)
            async def collect():
                process.stdin.write(encode(request))
                await process.stdin.drain()
                process.stdin.close()
                output = bytearray()
                while chunk := await process.stdout.read(4096):
                    output.extend(chunk)
                    if len(output) > MAX_WIRE: raise InfraredUnavailable('Infrared response exceeded its limit.')
                await process.wait()
                if process.returncode != 0: raise InfraredUnavailable('Infrared worker stopped unexpectedly.')
                return validate_result(request['action'], decode(bytes(output)))
            return await asyncio.wait_for(collect(), DEADLINES[request['action']])
        except (OSError, TimeoutError, InfraredError, ValueError):
            if request['action'] == 'send' and process is not None:
                return send_result()  # Dispatch may have happened; never retry.
            raise InfraredUnavailable('USB infrared operation could not finish. Check the adapter.') from None
        finally:
            if process is None and spawning.done() and not spawning.cancelled():
                with suppress(Exception): process = spawning.result()
            if process is not None:
                cleanup = asyncio.create_task(self.reap(process))
                self.retain(cleanup)
                try: await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    self.poisoned = True
                    raise
            elif not spawning.done():
                self.poisoned = True
                spawning.add_done_callback(self.late_spawn)
                self.retain(spawning)


class Broker:
    def __init__(self, owner, worker=None, clock=monotonic):
        self.owner = owner
        self.worker = worker or Worker()
        self.clock = clock
        self.lock = asyncio.Lock()
        self.next_operation = 0
        self.connections = 0

    async def execute(self, request):
        request = validate_request(request)
        if self.lock.locked() or self.clock() < self.next_operation:
            raise InfraredBusy('Infrared service is busy. Wait before trying again.')
        async with self.lock:
            try: return await self.worker.run(request)
            finally: self.next_operation = self.clock() + .5

    def peer_allowed(self, writer):
        try:
            peer = writer.get_extra_info('socket').getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            return struct.unpack('3i', peer)[1] == self.owner
        except (OSError, AttributeError, TypeError, struct.error):
            return False

    async def handle(self, reader, writer):
        operation = watcher = None
        admitted = False
        result = None
        try:
            if not self.peer_allowed(writer): return
            if self.connections >= 8: return
            self.connections += 1
            admitted = True
            request = validate_request(decode(await asyncio.wait_for(reader.readline(), 3)))
            # Client disappearance/cancel or pipelined bytes revoke this request.
            # A late successful transmission is still unconfirmed, never replayed.
            watcher = asyncio.create_task(reader.read(1))
            # Give already-buffered EOF/pipelined data a chance to reject before
            # any worker is dispatched, not merely cancel after it has started.
            await asyncio.sleep(0)
            if watcher.done(): return
            operation = asyncio.create_task(self.execute(request))
            done, _ = await asyncio.wait({operation, watcher}, return_when=asyncio.FIRST_COMPLETED)
            if watcher in done: return
            result = await operation
        except InfraredBusy:
            result = {'error': 'Infrared service is busy. Wait before trying again.'}
        except (ValueError, OSError, TimeoutError):
            result = {'error': 'Infrared request could not finish. Check setup and try again.'}
        finally:
            for task in (watcher, operation):
                if task is not None:
                    if not task.done(): task.cancel()
                    with suppress(asyncio.CancelledError, Exception): await task
            if admitted: self.connections -= 1
            if result is not None:
                with suppress(Exception):
                    writer.write(encode(result))
                    await asyncio.wait_for(writer.drain(), 2)
            writer.close()
            with suppress(Exception): await asyncio.wait_for(writer.wait_closed(), 2)


async def ir_request(request):
    """Application client. One request only; cancellation closes the worker lease."""
    request = validate_request(request)
    if not hasattr(asyncio, 'open_unix_connection'):
        raise InfraredUnavailable('Local USB infrared service is unavailable on this system.')
    writer = None
    dispatched = False
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(SOCKET, limit=MAX_WIRE), 2)
        payload = encode(request)
        dispatched = True
        writer.write(payload)
        await asyncio.wait_for(writer.drain(), 2)
        result = validate_result(request['action'], decode(await asyncio.wait_for(reader.readline(), 20)))
    except (OSError, TimeoutError, NotImplementedError, ValueError):
        if dispatched and request['action'] == 'send': return send_result()
        raise InfraredUnavailable('Local USB infrared service is unavailable.') from None
    finally:
        if writer is not None:
            writer.close()
            with suppress(Exception): await asyncio.wait_for(writer.wait_closed(), 2)
    if 'error' in result: raise InfraredError(result['error'])
    return result


async def serve():
    import pwd
    if (sys.platform != 'linux' or os.geteuid() != pwd.getpwnam('luma-ir').pw_uid
            or os.geteuid() == 0 or os.environ.get('LISTEN_PID') != str(os.getpid())
            or os.environ.get('LISTEN_FDS') != '1'):
        raise RuntimeError('Start through luma-ir.socket as the dedicated luma-ir user.')
    broker = Broker(pwd.getpwnam('luma').pw_uid)
    listener = socket.socket(fileno=3)
    if listener.family != socket.AF_UNIX or listener.getsockname() != SOCKET:
        listener.close()
        raise RuntimeError('Invalid infrared activation socket.')
    server = await asyncio.start_unix_server(broker.handle, sock=listener, limit=MAX_WIRE, backlog=8)
    async with server:
        await server.serve_forever()


def main():
    asyncio.run(serve())
