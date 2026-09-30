"""Root-owned socket broker for verified, atomic Luma application updates."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import time
from contextlib import suppress

from .update_agent import MAX_BUNDLE_BYTES, PUBLIC_KEY, RELEASES_ROOT, UpdateError, apply_bundle, staged_bundle, verify_bundle


SOCKET = "/run/luma-update.sock"
MAX_WIRE = ((MAX_BUNDLE_BYTES + 2) // 3) * 4 + 4096
log = logging.getLogger(__name__)
STATUS_PATH = RELEASES_ROOT / '.luma-update-status.json'
PHASES = frozenset({'idle','verifying','copying','installing','syncing','switching',
                    'restarting','checking','restoring','complete','failed','interrupted'})


class ProgressStore:
    """Root-owned, non-secret progress record outside every replaceable release."""

    def __init__(self, path: Path):
        self.path=path

    def read(self):
        try:
            if self.path.is_symlink() or self.path.stat().st_size>4096:
                return None
            value=json.loads(self.path.read_text(encoding='utf-8'))
            if (not isinstance(value,dict) or value.get('state') not in {'installing','installed','failed'}
                    or value.get('phase') not in PHASES
                    or not isinstance(value.get('target_version'),str)
                    or not isinstance(value.get('started_epoch'),(int,float))
                    or not isinstance(value.get('message'),str)
                    or len(value['message'])>300):
                return None
            return value
        except (OSError,ValueError,TypeError,KeyError):
            return None

    def write(self,value):
        parent=self.path.parent
        if parent.is_symlink() or not parent.is_dir():
            raise UpdateError('The protected update-progress directory is unavailable.')
        temporary=parent / f'.{self.path.name}.{secrets.token_hex(8)}.tmp'
        descriptor=-1
        try:
            descriptor=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),0o600)
            with os.fdopen(descriptor,'wb') as stream:
                descriptor=-1
                stream.write(json.dumps(value,sort_keys=True,separators=(',',':')).encode('utf-8')+b'\n')
                stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,self.path)
            directory=os.open(parent,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
            try:os.fsync(directory)
            finally:os.close(directory)
        except OSError:
            raise UpdateError('Could not persist the local update status.') from None
        finally:
            if descriptor>=0:os.close(descriptor)
            if temporary.exists():temporary.unlink()


def validate_request(value):
    if not isinstance(value, dict) or value.get("action") not in {"status", "install"}:
        raise ValueError("Invalid Luma update request.")
    action = value["action"]
    if set(value) != ({"action"} if action == "status" else {"action", "bundle"}):
        raise ValueError("Invalid Luma update request.")
    if action == "install" and (not isinstance(value["bundle"], str)
                                  or len(value["bundle"]) > ((MAX_BUNDLE_BYTES + 2) // 3) * 4):
        raise ValueError("Invalid Luma update bundle.")
    return value


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def _peer_is_luma(writer):
    try:
        import pwd
        peer = writer.get_extra_info("socket").getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        return struct.unpack("3i", peer)[1] == pwd.getpwnam("luma").pw_uid
    except (AttributeError, OSError, KeyError, struct.error):
        return False


class UpdateBroker:
    """Verify requests as root, then install outside the API process lifetime."""

    def __init__(self, *, installer=apply_bundle, public_key_path: Path = PUBLIC_KEY,
                 refresh_service=None, status_path: Path | None = None):
        self.installer = installer
        self.public_key_path = public_key_path
        self.refresh_service = refresh_service
        self.state = "idle"
        self.version: str | None = None
        self.message = ""
        self.phase = 'idle'
        self.started_epoch: float | None = None
        self.store=ProgressStore(status_path) if status_path is not None else None
        saved=self.store.read() if self.store else None
        if saved:
            self.state=saved['state'];self.phase=saved['phase']
            self.version=saved['target_version'];self.message=saved['message']
            self.started_epoch=saved['started_epoch']
            if self.state=='installing':
                self._record('failed','interrupted',
                             'The update process was interrupted. Check the active version before trying recovery.')
        self._lock = asyncio.Lock()

    def status(self):
        elapsed=max(0,int(time.time()-self.started_epoch)) if self.started_epoch is not None else 0
        return {"state": self.state, "phase": self.phase,
                "target_version": self.version, "message": self.message,
                "elapsed_seconds": elapsed}

    def _record(self,state,phase,message,*,required=False):
        self.state=state;self.phase=phase;self.message=message
        if self.store:
            try:
                self.store.write({'state':state,'phase':phase,'target_version':self.version,
                                  'started_epoch':self.started_epoch,'message':message})
            except UpdateError:
                if required:raise
                log.exception('Could not persist Luma update progress')

    def _progress(self,phase):
        if phase not in PHASES:raise UpdateError('The installer reported an invalid progress phase.')
        self._record('installing',phase,'Keep power connected while Luma installs the verified update.')

    async def accept(self, value):
        value = validate_request(value)
        if value["action"] == "status":
            return self.status(), None
        if self._lock.locked() or self.state == "installing":
            return {"error": "A Luma update is already being installed."}, None
        try:
            bundle = base64.b64decode(value["bundle"], validate=True)
        except (ValueError, TypeError):
            return {"error": "The Luma update bundle is invalid."}, None
        if not bundle or len(bundle) > MAX_BUNDLE_BYTES:
            return {"error": "The Luma update bundle is too large."}, None
        async with self._lock:
            if self.state == "installing":
                return {"error": "A Luma update is already being installed."}, None
            try:
                verified = await asyncio.to_thread(self._verify, bundle)
            except UpdateError as error:
                return {"error": str(error)}, None
            self.version = verified["version"]
            self.started_epoch=time.time()
            try:
                self._record('installing','verifying','Keep power connected while Luma installs the verified update.',required=True)
            except UpdateError as error:
                self.state='idle';self.phase='idle';self.version=None;self.started_epoch=None
                return {'error':str(error)},None
        return {"accepted": True, "version": self.version}, bundle

    def _verify(self, bundle):
        with staged_bundle(bundle, prefix="luma-update-verify-") as bundle_path:
            return verify_bundle(bundle_path, self.public_key_path)

    async def install(self, bundle):
        try:
            with staged_bundle(bundle, prefix="luma-update-") as bundle_path:
                await asyncio.to_thread(self.installer, bundle_path,
                                        public_key_path=self.public_key_path,progress=self._progress)
            self._record('installed','complete','The new release passed its local health check.')
            if self.refresh_service is not None:
                try:
                    await asyncio.to_thread(self.refresh_service)
                except Exception:
                    # The application is already healthy and committed. Keep
                    # that result truthful; a broker refresh failure is
                    # recoverable by reboot and must not imply app rollback.
                    log.exception("Could not refresh the Luma update broker after installation")
        except UpdateError as error:
            self._record('failed','failed',str(error))
        except Exception:
            self._record('failed','failed','The update failed. Check the active version before retrying.')


async def _serve_listener(listener, broker):
    async def handle(reader, writer):
        task_bundle = None
        result = {"error": "Luma update operation failed."}
        try:
            if not _peer_is_luma(writer):
                return
            raw = await asyncio.wait_for(reader.readline(), 60)
            if not raw or len(raw) > MAX_WIRE:
                raise ValueError()
            request = json.loads(raw, object_pairs_hook=_no_duplicates)
            result, task_bundle = await broker.accept(request)
        except (ValueError, json.JSONDecodeError, asyncio.TimeoutError):
            result = {"error": "Invalid or expired Luma update request."}
        except Exception:
            result = {"error": "Luma update service is unavailable. Use Pi Connect for recovery."}
        finally:
            if not writer.is_closing():
                with suppress(Exception):
                    writer.write(json.dumps(result, separators=(",", ":")).encode() + b"\n")
                    await writer.drain()
                writer.close()
                with suppress(Exception):
                    await writer.wait_closed()
        if task_bundle is not None:
            asyncio.create_task(broker.install(task_bundle))

    server = await asyncio.start_unix_server(handle, sock=listener, limit=MAX_WIRE)
    async with server:
        await server.serve_forever()


async def serve():
    if (os.geteuid() != 0 or os.environ.get("LISTEN_PID") != str(os.getpid())
            or os.environ.get("LISTEN_FDS") != "1"):
        raise RuntimeError("Start through luma-update.socket")
    listener = socket.socket(fileno=3)
    await _serve_listener(listener, UpdateBroker(refresh_service=_restart_service,status_path=STATUS_PATH))


def _restart_service():
    """Reload the broker from the newly selected app release after success."""
    subprocess.run(
        ["/usr/bin/systemctl", "--no-block", "restart", "luma-update.service"],
        check=True, timeout=8, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


async def update_request(request):
    """Call the root broker; only a verified Luma bundle can change the app."""
    validate_request(request)
    writer = None
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(SOCKET, limit=MAX_WIRE), 4)
        payload = json.dumps(request, separators=(",", ":")).encode() + b"\n"
        if len(payload) > MAX_WIRE:
            raise ValueError()
        writer.write(payload)
        await writer.drain()
        raw = await asyncio.wait_for(reader.readline(), 65)
        if not raw or len(raw) > 4096:
            raise ValueError()
        result = json.loads(raw, object_pairs_hook=_no_duplicates)
        if not isinstance(result, dict):
            raise ValueError()
        if "error" in result:
            raise UpdateError(result["error"])
        return result
    except UpdateError:
        raise
    except (OSError, TimeoutError, ValueError, json.JSONDecodeError, asyncio.IncompleteReadError):
        raise UpdateError("Luma update service is unavailable. Use Pi Connect for recovery.") from None
    finally:
        if writer:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()


def main():
    asyncio.run(serve())
