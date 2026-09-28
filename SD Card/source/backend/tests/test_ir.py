import asyncio
from collections import deque
from copy import deepcopy
import json
from pathlib import Path
import stat
import struct
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from luma import ir_broker as broker, ir_linux as linux
from luma.ir_protocol import (InfraredBusy, InfraredError, InfraredUnavailable, MAX_WIRE,
                              decode, encode, send_result, validate_result)
from luma.ir_signal import Frame, carrier, signal, signal_key

ID = 'usb-ir-' + 'a' * 24
RAW = {'carrier_hz': 38000, 'durations': [9000, 4500, 560, 560, 560, 1690, 560]}
LEARN = {'action': 'learn', 'device_id': ID, 'carrier_hz': None}
SEND = {'action': 'send', 'device_id': ID, 'emitter': None, 'signal': RAW}
PUBLIC = {'id': ID, 'name': 'USB adapter', 'serial_present': True, 'receive': True, 'send': True,
          'measure_carrier': True, 'emitter_selection': False}


def words(raw=RAW, *, frequency=True, delimiter=0x03000000 | 25000):
    return ([0x02000000 | raw['carrier_hz']] if frequency else []) + [
        value | (0x01000000 if index % 2 == 0 else 0) for index, value in enumerate(raw['durations'])
    ] + ([] if delimiter is None else [delimiter])


def packed(items): return struct.pack(f'={len(items)}I', *items)


@pytest.mark.parametrize('bad', [True, 19999, 60001, '38000', 38000.0, None])
def test_carrier_is_explicit_not_guessed(bad):
    with pytest.raises(InfraredError): carrier(bad)
    assert carrier(None, optional=True) is None


@pytest.mark.parametrize('bad', [[], {}, {**RAW, 'path': '/dev/lirc0'}, {**RAW, 'durations': [10] * 6},
                                {**RAW, 'durations': [10] * 513}, {**RAW, 'durations': [19999] * 15},
                                {**RAW, 'durations': [True] * 7}, {**RAW, 'durations': [20000] * 7}])
def test_signal_limits(bad):
    with pytest.raises(InfraredError): signal(bad)


def test_signal_copy_stable_key_and_complete_frame():
    result = signal(RAW)
    result['durations'][0] = 3
    assert RAW['durations'][0] == 9000
    assert signal_key(RAW) == signal_key(dict(reversed(list(RAW.items()))))
    frame = Frame()
    frame.feed(10000)
    for word in words(): frame.feed(word)
    assert frame.result() == {**RAW, 'carrier_source': 'measured'}
    frame.feed(0x04000000)  # Later repeats are outside this one captured frame.
    assert frame.result()['durations'] == RAW['durations']


def test_no_silence_guess_or_short_timeout_completion():
    frame = Frame(38000)
    for word in words(frequency=False, delimiter=None): frame.feed(word)
    frame.feed(0x03000000 | 3000)
    assert not frame.complete
    with pytest.raises(InfraredError): frame.result()
    frame.feed(30000)
    assert frame.result()['carrier_source'] == 'owner_supplied'


@pytest.mark.parametrize('bad', [0x04000000, 0x05000000, True, -1, 2**32, 0x01000000])
def test_malformed_receiver_words_fail(bad):
    with pytest.raises(InfraredError): Frame(38000).feed(bad)


def test_carrier_drift_wrong_order_short_repeat_and_missing_carrier():
    frame = Frame()
    frame.feed(0x02000000 | 38000)
    with pytest.raises(InfraredError): frame.feed(0x02000000 | 56000)
    frame = Frame(38000)
    frame.feed(0x01000000 | 9000)
    with pytest.raises(InfraredError): frame.feed(0x01000000 | 100)
    for raw in ({**RAW, 'durations': [9000, 2250, 560]}, RAW):
        frame = Frame()
        for word in words(raw, frequency=False): frame.feed(word)
        with pytest.raises(InfraredError): frame.result()


@pytest.mark.parametrize('bad', [None, [], {}, {'action': []}, {'action': 'shell'},
                                {**SEND, 'device_id': '/dev/lirc0'}, {**SEND, 'emitter': True},
                                {**SEND, 'emitter': 33}, {**LEARN, 'extra': 1}])
def test_request_allowlist(bad):
    with pytest.raises(InfraredError): linux.validate_request(bad)


@pytest.mark.parametrize('raw', [b'{}', b'{}\n{}\n', b'{"action":"discover","action":"send"}\n',
                               b'{"a":NaN}\n', b'{"a":Infinity}\n', b'[]\n', b'\xff\n',
                               b'x' * MAX_WIRE + b'\n', b'{}\r\n'])
def test_wire_rejects_duplicates_nonfinite_oversize_and_multiple_messages(raw):
    with pytest.raises(InfraredError): decode(raw)


def test_protocol_does_not_expose_internal_paths_or_unbounded_helper_messages():
    assert decode(encode(SEND)) == SEND
    assert validate_result('discover', {'devices': [PUBLIC]})['devices'] == [PUBLIC]
    for value in ({'devices': [{**PUBLIC, '_path': '/dev/lirc0'}]}, {'devices': [PUBLIC, PUBLIC]},
                  {'devices': [{**PUBLIC, 'send': 1}]}, {'error': 'x' * 201}, {'error': 'bad\nvalue'}):
        with pytest.raises(InfraredUnavailable): validate_result('discover', value)
    assert validate_result('send', {'status': 'unknown', 'message': 'do not echo me'}) == send_result()


def fake_fd(monkeypatch):
    monkeypatch.setattr(linux, 'open_checked', lambda _: 42)
    calls, closed = [], []
    def ioctl(fd, request, value=0):
        calls.append((request, value))
        return 0, 4 if request == linux.GET_REC_MODE else 0
    monkeypatch.setattr(linux, 'ioctl_word', ioctl)
    monkeypatch.setattr(linux.os, 'close', closed.append)
    return calls, closed


def test_one_write_no_retry_on_short_write_or_oserror(monkeypatch):
    calls, closed = fake_fd(monkeypatch)
    writes = []
    def write(fd, payload): writes.append(payload); return len(payload) - 4
    monkeypatch.setattr(linux.os, 'write', write)
    assert linux.transmit(PUBLIC, None, RAW)['status'] == 'unknown'
    assert len(writes) == 1 and writes[0] == packed(RAW['durations']) and closed == [42]
    def failed(fd, payload): writes.append(payload); raise OSError('private device error')
    monkeypatch.setattr(linux.os, 'write', failed)
    assert linux.transmit(PUBLIC, None, RAW) == send_result()
    assert len(writes) == 2


def test_emitter_selection_carrier_and_mask_checked_before_transmit(monkeypatch):
    calls, _ = fake_fd(monkeypatch)
    writes = []
    monkeypatch.setattr(linux.os, 'write', lambda fd, data: writes.append(data) or len(data))
    assert linux.transmit({**PUBLIC, 'emitter_selection': True}, 2, RAW)['status'] == 'sent_unconfirmed'
    assert (linux.SET_CARRIER, 38000) in calls and (linux.SET_MASK, 2) in calls
    with pytest.raises(InfraredError): linux.transmit(PUBLIC, 2, RAW)
    monkeypatch.setattr(linux, 'ioctl_word', lambda fd, req, value: (4 if req == linux.SET_MASK else 0, value))
    with pytest.raises(InfraredError, match='not supported'):
        linux.transmit({**PUBLIC, 'emitter_selection': True}, 5, RAW)
    assert len(writes) == 1


def setup_capture(monkeypatch, chunks):
    calls, closed = fake_fd(monkeypatch)
    chunks = deque(chunks)
    tick = [0]
    def clock(): tick[0] += .15; return tick[0]
    def read(fd, count):
        item = chunks.popleft() if chunks else BlockingIOError()
        if isinstance(item, Exception): raise item
        return item
    monkeypatch.setattr(linux.os, 'read', read)
    monkeypatch.setattr(linux.select, 'select', lambda *args: ([42] if chunks else [], [], []))
    monkeypatch.setattr(linux.time, 'monotonic', clock)
    return calls, closed


def test_learn_flushes_previous_press_and_restores_modes(monkeypatch):
    old = packed(words({**RAW, 'carrier_hz': 56000}))
    calls, closed = setup_capture(monkeypatch, [old, BlockingIOError(), packed(words())])
    assert linux.learn(PUBLIC, None) == {**RAW, 'carrier_source': 'measured'}
    assert calls[-2:] == [(linux.SET_MEASURE, 0), (linux.SET_REC_MODE, 4)]
    assert closed == [42]


@pytest.mark.parametrize('payload', [packed(words(delimiter=None)), b'', b'abc', packed([0x04000000])])
def test_learning_rejects_truncation_disconnect_and_overflow(monkeypatch, payload):
    _, closed = setup_capture(monkeypatch, [BlockingIOError(), payload])
    with pytest.raises(InfraredError): linux.learn(PUBLIC, None)
    assert closed == [42]


def test_receiver_noise_and_missing_carrier_do_not_learn(monkeypatch):
    _, closed = setup_capture(monkeypatch, [packed(words())] * 8)
    with pytest.raises(InfraredError, match='busy'): linux.learn(PUBLIC, None)
    assert closed == [42]
    with pytest.raises(InfraredError, match='documentation'):
        linux.learn({**PUBLIC, 'measure_carrier': False}, None)


def test_open_checked_rejects_hotplug_identity_change(monkeypatch):
    entry = {**PUBLIC, '_path': '/dev/lirc0', '_rdev': 4, '_features': 6,
             '_sysnode': '/sys/class/lirc/lirc0', '_devices_root': '/sys/devices', '_identity': ['old']}
    for key in ('O_NONBLOCK', 'O_CLOEXEC', 'O_NOFOLLOW'): monkeypatch.setattr(linux.os, key, 0, raising=False)
    monkeypatch.setattr(linux.os, 'open', lambda *args: 42)
    monkeypatch.setattr(linux.os, 'fstat', lambda fd: SimpleNamespace(st_mode=stat.S_IFCHR, st_rdev=4))
    monkeypatch.setattr(linux, 'ioctl_word', lambda *args: (0, 6))
    monkeypatch.setattr(linux, 'usb_identity', lambda *args: (['new'], 'new', True))
    closed = []
    monkeypatch.setattr(linux.os, 'close', closed.append)
    with pytest.raises(InfraredError, match='changed'): linux.open_checked(entry)
    assert closed == [42]


class Process:
    def __init__(self, output=b'{"devices":[]}\n', *, hang=False, code=0):
        self.returncode = None if hang else code
        self.stdout = asyncio.StreamReader()
        if output: self.stdout.feed_data(output)
        if not hang: self.stdout.feed_eof()
        self.stdin = SimpleNamespace(write=lambda data: self.input.append(data), drain=AsyncMock(), close=lambda: None)
        self.input = []
        self.kills = 0
    def kill(self): self.kills += 1; self.returncode = -9; self.stdout.feed_eof()
    async def wait(self):
        while self.returncode is None: await asyncio.sleep(.001)
        return self.returncode


@pytest.mark.asyncio
async def test_worker_fixed_isolated_command_and_no_input_in_argv():
    process = Process()
    spawn = AsyncMock(return_value=process)
    assert await broker.Worker(spawn).run({'action': 'discover'}) == {'devices': []}
    args, kwargs = spawn.call_args
    assert args == (broker.sys.executable, '-I', '-m', 'luma.ir_linux')
    assert kwargs['stderr'] == asyncio.subprocess.DEVNULL and 'PYTHONPATH' not in kwargs['env']
    assert process.input == [b'{"action":"discover"}\n']


@pytest.mark.asyncio
@pytest.mark.parametrize('output,code', [(b'x' * (MAX_WIRE + 1), 0), (b'bad\n', 0), (b'{}\n', 1)])
async def test_worker_failed_output_is_unknown_after_possible_send(output, code):
    process = Process(output, code=code)
    spawn = AsyncMock(return_value=process)
    assert await broker.Worker(spawn).run(SEND) == send_result()
    assert spawn.await_count == 1 and len(process.input) == 1


@pytest.mark.asyncio
async def test_worker_deadline_kills_reaps_and_never_retries(monkeypatch):
    monkeypatch.setitem(broker.DEADLINES, 'send', .01)
    process = Process(b'', hang=True)
    spawn = AsyncMock(return_value=process)
    assert await broker.Worker(spawn).run(SEND) == send_result()
    assert process.kills == 1 and process.returncode == -9 and spawn.await_count == 1


@pytest.mark.asyncio
async def test_cancellation_kills_worker_and_propagates():
    process = Process(b'', hang=True)
    worker = broker.Worker(AsyncMock(return_value=process))
    task = asyncio.create_task(worker.run(LEARN))
    for _ in range(20):
        if process.input: break
        await asyncio.sleep(.001)
    assert process.input
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert process.kills == 1


@pytest.mark.asyncio
async def test_cancel_during_spawn_keeps_reference_and_kills_late_child():
    gate = asyncio.Event()
    process = Process(b'', hang=True)
    async def spawn(*args, **kwargs): await gate.wait(); return process
    worker = broker.Worker(spawn)
    task = asyncio.create_task(worker.run(LEARN))
    await asyncio.sleep(.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert worker.poisoned
    gate.set()
    for _ in range(30):
        if process.kills: break
        await asyncio.sleep(.001)
    assert process.kills == 1
    with pytest.raises(InfraredUnavailable): await worker.run({'action': 'discover'})


@pytest.mark.asyncio
async def test_global_busy_rejects_instead_of_queuing_and_paces_after_cancellation():
    gate = asyncio.Event()
    async def work(_): await gate.wait(); return {'devices': []}
    clock = [1.0]
    worker = SimpleNamespace(run=AsyncMock(side_effect=work))
    instance = broker.Broker(1000, worker, clock=lambda: clock[0])
    task = asyncio.create_task(instance.execute({'action': 'discover'}))
    await asyncio.sleep(0)
    with pytest.raises(InfraredBusy): await instance.execute(LEARN)
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    with pytest.raises(InfraredBusy): await instance.execute({'action': 'discover'})
    clock[0] += 1
    gate.set()
    assert await instance.execute({'action': 'discover'}) == {'devices': []}
    assert worker.run.await_count == 2


class Writer:
    def __init__(self, uid=1000):
        self.output = []
        self.closed = False
        self.uid = uid
    def get_extra_info(self, name): return self
    def getsockopt(self, *args): return struct.pack('3i', 10, self.uid, 1000)
    def write(self, data): self.output.append(data)
    async def drain(self): pass
    def close(self): self.closed = True
    async def wait_closed(self): pass


@pytest.mark.asyncio
async def test_peer_check_and_disconnect_cancel_lease(monkeypatch):
    monkeypatch.setattr(broker.socket, 'SO_PEERCRED', 17, raising=False)
    worker = SimpleNamespace(run=AsyncMock(return_value={'devices': []}))
    instance = broker.Broker(1000, worker)
    reader = asyncio.StreamReader()
    writer = Writer(999)
    await instance.handle(reader, writer)
    assert writer.closed and not writer.output and not worker.run.called
    # A disconnected authorized owner does not leave a learning worker behind.
    started, cancelled = asyncio.Event(), asyncio.Event()
    async def work(_):
        started.set()
        try: await asyncio.Event().wait()
        finally: cancelled.set()
    worker.run = AsyncMock(side_effect=work)
    reader.feed_data(encode(LEARN))
    writer = Writer()
    task = asyncio.create_task(instance.handle(reader, writer))
    await asyncio.wait_for(started.wait(), 1)
    reader.feed_eof()
    await asyncio.wait_for(task, 1)
    assert cancelled.is_set() and writer.closed and not writer.output and instance.connections == 0


@pytest.mark.asyncio
async def test_client_malformed_send_reply_unknown_no_retry(monkeypatch):
    reader = asyncio.StreamReader()
    reader.feed_data(b'not-json\n')
    writer = Writer()
    connect = AsyncMock(return_value=(reader, writer))
    monkeypatch.setattr(broker.asyncio, 'open_unix_connection', connect, raising=False)
    assert await broker.ir_request(SEND) == send_result()
    assert connect.await_count == 1 and writer.closed and len(writer.output) == 1


@pytest.mark.asyncio
async def test_client_connection_failure_is_not_a_transmission(monkeypatch):
    monkeypatch.setattr(broker.asyncio, 'open_unix_connection', AsyncMock(side_effect=OSError('internal path')), raising=False)
    with pytest.raises(InfraredUnavailable, match='unavailable'): await broker.ir_request(SEND)


def test_worker_on_unsupported_platform_never_opens_hardware(monkeypatch):
    monkeypatch.setattr(linux.sys, 'platform', 'win32')
    monkeypatch.setattr(linux.os, 'open', lambda *args: pytest.fail('must not open a device'))
    assert linux.execute({'action': 'discover'}) == {'devices': []}


@pytest.mark.asyncio
async def test_stuck_killed_process_disables_further_dispatch():
    process = Process(b'', hang=True)
    released = asyncio.Event()
    async def wait(): await released.wait(); return -9
    process.wait = wait
    process.kill = lambda: None
    worker = broker.Worker()
    await worker.reap(process)
    assert worker.poisoned and worker.pending
    with pytest.raises(InfraredUnavailable): await worker.run(SEND)
    released.set()
    await asyncio.gather(*worker.pending)


@pytest.mark.asyncio
async def test_failed_spawn_has_no_send_and_does_not_retry():
    spawn = AsyncMock(side_effect=OSError('private executable path'))
    worker = broker.Worker(spawn)
    with pytest.raises(InfraredUnavailable): await worker.run(SEND)
    assert spawn.await_count == 1
