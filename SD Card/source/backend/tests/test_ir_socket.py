"""Linux kernel Unix-socket checks using synthetic workers, never /dev/lirc."""
import asyncio
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from luma import ir_broker as broker
from luma.ir_protocol import InfraredError, InfraredUnavailable, decode, encode, send_result

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(sys.platform != 'linux', reason='Linux SO_PEERCRED required')]

SEND = {'action': 'send', 'device_id': 'usb-ir-' + 'a' * 24, 'emitter': None,
        'signal': {'carrier_hz': 38000, 'durations': [9000, 4500, 560, 560, 560, 560, 560]}}


async def test_real_socket_authorized_roundtrip_and_wrong_uid_rejection(tmp_path, monkeypatch):
    # Use /tmp (short path), not an untrusted destination or any system socket.
    path = str(tmp_path / 'ir.sock')
    worker = SimpleNamespace(run=AsyncMock(return_value={'devices': []}))
    instance = broker.Broker(os.getuid(), worker)
    server = await asyncio.start_unix_server(instance.handle, path=path, limit=16384)
    monkeypatch.setattr(broker, 'SOCKET', path)
    try:
        assert await broker.ir_request({'action': 'discover'}) == {'devices': []}
        assert worker.run.await_count == 1
        instance.owner = os.getuid() + 1
        with pytest.raises(InfraredUnavailable): await broker.ir_request({'action': 'discover'})
        assert worker.run.await_count == 1
    finally:
        server.close()
        await server.wait_closed()


async def test_real_socket_disconnect_revokes_learning_and_busy_is_not_queued(tmp_path, monkeypatch):
    started, stopped = asyncio.Event(), asyncio.Event()
    async def run(_):
        started.set()
        try: await asyncio.Event().wait()
        finally: stopped.set()
    worker = SimpleNamespace(run=AsyncMock(side_effect=run))
    instance = broker.Broker(os.getuid(), worker)
    path = str(tmp_path / 'ir.sock')
    server = await asyncio.start_unix_server(instance.handle, path=path, limit=16384)
    monkeypatch.setattr(broker, 'SOCKET', path)
    reader, writer = await asyncio.open_unix_connection(path)
    try:
        writer.write(encode({'action': 'learn', 'device_id': SEND['device_id'], 'carrier_hz': 38000}))
        await writer.drain()
        await asyncio.wait_for(started.wait(), 1)
        with pytest.raises(InfraredError, match='busy'): await broker.ir_request(SEND)
        assert worker.run.await_count == 1
        writer.close()
        await writer.wait_closed()
        await asyncio.wait_for(stopped.wait(), 1)
    finally:
        writer.close()
        server.close()
        await server.wait_closed()


async def test_real_socket_rejects_duplicate_keys_and_pipelining(tmp_path):
    worker = SimpleNamespace(run=AsyncMock(return_value={'devices': []}))
    instance = broker.Broker(os.getuid(), worker)
    path = str(tmp_path / 'ir.sock')
    server = await asyncio.start_unix_server(instance.handle, path=path, limit=16384)
    try:
        reader, writer = await asyncio.open_unix_connection(path)
        writer.write(b'{"action":"discover","action":"send"}\n')
        await writer.drain()
        assert 'error' in decode(await asyncio.wait_for(reader.readline(), 1))
        writer.close()
        await writer.wait_closed()
        assert not worker.run.called
        # Pipeline rejection must not dispatch even the first frame.
        reader, writer = await asyncio.open_unix_connection(path)
        writer.write(b'{"action":"discover"}\n{"action":"discover"}\n')
        await writer.drain()
        assert await asyncio.wait_for(reader.read(), 1) == b''
        writer.close()
        await writer.wait_closed()
        assert not worker.run.called
    finally:
        server.close()
        await server.wait_closed()
