import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from luma.api import create_app
from luma.room import Room
from luma.room_runtime import RoomRuntime, RoomAccessChanged
from luma.purifier_adapter import PurifierAdapter, PurifierBusy, PurifierRateLimit, PurifierReconnect, PurifierUnavailable
from luma.service import LumaService
from luma.storage import Storage
from test_purifier_adapter import Provider, SECRET, DEVICES, BYPASS

NOW = datetime(2026, 9, 26, 20, tzinfo=UTC)
SELECTED = {'id': 'purifier-' + 'a' * 24, 'name': 'Bedroom purifier', 'model': 'Core300S'}


def configured(tmp_path):
    store = Room(Storage(tmp_path / 'room.db'))
    store.set_session(SECRET, revision=store.revision, generation=store.generation)
    store.select(SELECTED, revision=store.revision, generation=store.generation)
    return store


def test_session_selection_survive_restart_without_exporting_credentials(tmp_path):
    store = configured(tmp_path)
    restored = Room(store.storage)
    assert restored.selected == SELECTED and restored.session == SECRET
    assert restored.revision == store.revision and restored.generation != store.generation
    assert restored.sample is None and restored.health == 'unavailable'
    serialized = json.dumps(restored.configuration(NOW))
    assert all(value not in serialized for value in (SECRET['token'], SECRET['account_id']))
    assert restored.configuration(NOW)['remote_control'] is False


def test_session_replacement_disconnect_clear_selection_and_receipts_atomically(tmp_path):
    store = configured(tmp_path)
    store.claim('power', False, revision=store.revision, generation=store.generation, now=NOW)
    old_generation = store.generation
    store.set_session({**SECRET, 'account_id': 'NEW_ACCOUNT'}, revision=store.revision, generation=store.generation)
    assert store.selected is None and store.receipt is None and store.sample is None
    assert store.generation != old_generation
    store.set_session(None, revision=store.revision, generation=store.generation)
    assert store.storage.get_secret('room.vesync') is None and store.session is None
    assert store.storage.get_cache('room', 'purifier_command') is None


def test_disk_failure_does_not_change_live_or_saved_session(tmp_path, monkeypatch):
    store = configured(tmp_path)
    before, secret = store.configuration(NOW), store.session
    from contextlib import contextmanager
    @contextmanager
    def failed(): raise OSError('test storage failure'); yield
    monkeypatch.setattr(store.storage, 'transaction', failed)
    with pytest.raises(OSError): store.set_session(None, revision=store.revision, generation=store.generation)
    assert store.configuration(NOW) == before and store.session == secret


@pytest.mark.parametrize('raw', [{'version': 7}, [], {'version': 1, 'revision': 'bad', 'selected': SELECTED}])
def test_corrupt_configuration_preserved_readonly(tmp_path, raw):
    storage = Storage(tmp_path / 'room.db')
    storage.set_cache('room', 'purifier', raw)
    store = Room(storage)
    assert store.recovery_error and store.selected is None
    with pytest.raises(ValueError, match='recovery'): store.set_session(None, revision=store.revision, generation=store.generation)
    assert storage.get_cache('room', 'purifier') == raw


def test_command_claim_survives_restart_as_unconfirmed_and_never_replays(tmp_path):
    store = configured(tmp_path)
    key = store.claim('speed', 3, revision=store.revision, generation=store.generation, now=NOW)
    restored = Room(store.storage)
    assert restored.receipt['id'] == key and restored.receipt['status'] == 'unconfirmed'
    assert restored.receipt['accepted'] is None
    assert restored.receipt['override_until'] == (NOW + timedelta(hours=1)).isoformat()
    assert not restored.finish(key, {'status': 'confirmed', 'accepted': True}, revision=store.revision, generation=store.generation)


def test_purifier_override_survives_selection_edits_and_account_disconnect(tmp_path):
    store = configured(tmp_path)
    store.claim('power', False, revision=store.revision, generation=store.generation, now=NOW)
    store.select(None, revision=store.revision, generation=store.generation)
    assert store.receipt is None and store.override_active(NOW)
    restored = Room(store.storage)
    assert restored.override_active(NOW + timedelta(minutes=59))
    restored.set_session(None, revision=restored.revision, generation=restored.generation)
    assert Room(store.storage).override_active(NOW)
    assert not Room(store.storage).override_active(NOW + timedelta(hours=1))


def test_purifier_scene_does_not_extend_manual_override_and_legacy_migrates_on_edit(tmp_path):
    store = configured(tmp_path)
    store.claim('power', False, revision=store.revision, generation=store.generation, now=NOW)
    with store.storage.transaction() as connection:
        connection.execute("DELETE FROM cache WHERE namespace='room' AND key='purifier_override'")
    legacy = Room(store.storage)
    assert legacy.override_active(NOW)
    legacy.select(SELECTED, revision=legacy.revision, generation=legacy.generation)
    restored = Room(store.storage)
    with pytest.raises(ValueError, match='override'):
        restored.claim('power', True, revision=restored.revision, generation=restored.generation, now=NOW, kind='scene')
    restored.claim('power', True, revision=restored.revision, generation=restored.generation, now=NOW + timedelta(hours=1), kind='scene')
    assert restored.override_until == (NOW + timedelta(hours=1)).isoformat()
    assert not Room(store.storage).override_active(NOW + timedelta(hours=1, seconds=1))


def test_corrupt_purifier_override_disables_without_overwrite(tmp_path):
    store = configured(tmp_path)
    store.storage.set_cache('room', 'purifier_override', {'unexpected': 'value'})
    restored = Room(store.storage)
    assert restored.recovery_error
    assert store.storage.get_cache('room', 'purifier_override') == {'unexpected': 'value'}


def test_purifier_receipt_and_override_roll_back_together(tmp_path, monkeypatch):
    store = configured(tmp_path)
    def fail(*args): raise OSError('Failure after receipt SQL, before override SQL')
    monkeypatch.setattr(store, '_write_override', fail)
    with pytest.raises(OSError):
        store.claim('power', False, revision=store.revision, generation=store.generation, now=NOW)
    assert store.receipt is None and store.override_until is None
    assert store.storage.get_cache('room', 'purifier_command') is None
    assert store.storage.get_cache('room', 'purifier_override') is None


def test_stale_revisions_and_old_poll_results_cannot_modify_new_selection(tmp_path):
    store = configured(tmp_path)
    revision, generation = store.revision, store.generation
    store.select(None, revision=revision, generation=generation)
    with pytest.raises(ValueError, match='changed'): store.select(SELECTED, revision=revision, generation=generation)
    assert not store.report({'id': SELECTED['id']}, revision=revision, generation=generation)


def test_readings_expire_and_do_not_write_each_snapshot(tmp_path, monkeypatch):
    store = configured(tmp_path)
    sample = {'id': SELECTED['id'], 'reported_at': NOW.isoformat(), 'state': {'power': True}, 'capabilities': {'power': True}}
    assert store.report(sample, revision=store.revision, generation=store.generation)
    monkeypatch.setattr(store.storage, 'set_cache', lambda *a, **k: pytest.fail('Snapshot wrote storage'))
    assert store.view(NOW)['fresh']
    assert not store.view(NOW + timedelta(minutes=6))['fresh']
    assert store.view(NOW + timedelta(minutes=6))['capabilities'] is None
    assert not store.view(NOW - timedelta(seconds=1))['fresh']


def runtime(tmp_path, provider=None):
    service = LumaService(Storage(tmp_path / 'service.db'), clock_trusted=lambda: True)
    provider = provider or Provider()
    ticks = [1000.0]
    def factory(saved=None, **kwargs): return PurifierAdapter(saved, transport=httpx.MockTransport(provider), **kwargs)
    rt = RoomRuntime(service, factory=factory, clock=lambda: ticks[0])
    return service, rt, provider, ticks


async def connect(rt, ticks):
    await rt.login('QA_EMAIL', 'QA_PASSWORD', 'US', rt.store.revision)
    ticks[0] += 5
    found = await rt.discover(rt.store.revision)
    await rt.select(found[0]['id'], 'QA selected purifier', rt.store.revision)
    ticks[0] += 5
    return found[0]['id']


@pytest.mark.asyncio
async def test_real_adapter_runtime_select_command_and_manual_override(tmp_path):
    service, rt, provider, ticks = runtime(tmp_path)
    try:
        key = await connect(rt, ticks)
        assert service.room.selected['id'] == key and service.room.sample
        result = await rt.command('speed', 3, service.room.revision)
        assert result['status'] == 'confirmed'
        assert service.room.receipt['status'] == 'confirmed'
        assert service.room.receipt['override_until']
        assert not await rt.refresh()  #120-second cadence, not another eager read.
        with pytest.raises(PurifierRateLimit): await rt.command('power', False, service.room.revision)
        ticks[0] += 120
        assert await rt.refresh()
        assert service.room.health == 'ready'
    finally: await rt.close()


@pytest.mark.asyncio
async def test_no_network_without_session_and_selection(tmp_path):
    service, rt, provider, ticks = runtime(tmp_path)
    try:
        assert not await rt.refresh() and not provider.calls
        service.room.set_session(SECRET, revision=service.room.revision, generation=service.room.generation)
        assert not await rt.refresh() and not provider.calls
    finally: await rt.close()


@pytest.mark.asyncio
async def test_reboot_restores_selection_and_polls_but_never_replays_command(tmp_path):
    service, rt, provider, ticks = runtime(tmp_path)
    await connect(rt, ticks)
    service.room.claim('power', False, revision=service.room.revision, generation=service.room.generation, now=datetime.now(UTC))
    await rt.close()
    service2 = LumaService(service.storage)
    rt2 = RoomRuntime(service2, factory=lambda saved=None, **kwargs: PurifierAdapter(saved, transport=httpx.MockTransport(provider), **kwargs))
    try:
        assert await rt2.refresh()
        assert provider.command_count == 0 and service2.room.receipt['status'] == 'unconfirmed'
    finally: await rt2.close()


@pytest.mark.asyncio
async def test_poll_failure_backs_off_and_auth_expiry_requires_reconnect(tmp_path):
    service, rt, provider, ticks = runtime(tmp_path)
    try:
        await connect(rt, ticks)
        original = deepcopy(service.room.sample)
        provider.fail = lambda _: httpx.Response(500)
        ticks[0] += 120
        assert not await rt.refresh() and service.room.sample == original
        assert service.room.health == 'unavailable'
        ticks[0] += 120
        provider.fail = lambda _: httpx.Response(401)
        assert not await rt.refresh() and rt.needs_reconnect
        count = len(provider.calls)
        ticks[0] += 10000
        assert not await rt.refresh() and len(provider.calls) == count
    finally: await rt.close()


@pytest.mark.asyncio
async def test_owner_lock_during_login_does_not_save_candidate_session(tmp_path):
    service, rt, provider, ticks = runtime(tmp_path)
    candidate = AsyncMock()
    async def login(*args):
        service.update_settings({'onboarding_completed': True})
        return SECRET
    candidate.login.side_effect = login
    rt.factory = lambda **kwargs: candidate
    with pytest.raises(RoomAccessChanged): await rt.login('QA_EMAIL', 'QA_PASSWORD', 'US', service.room.revision)
    assert service.room.session is None
    candidate.close.assert_awaited_once()
    await rt.close()


@pytest.mark.asyncio
async def test_disconnect_during_real_adapter_preflight_sends_no_command(tmp_path):
    provider = Provider()
    entered, release = asyncio.Event(), asyncio.Event()
    block = [False]
    async def delayed(request):
        response = provider(request)
        if block[0] and request.url.path == BYPASS:
            entered.set()
            await release.wait()
        return response
    service, rt, _, ticks = runtime(tmp_path, delayed)
    try:
        await connect(rt, ticks)
        block[0] = True
        command = asyncio.create_task(rt.command('power', False, service.room.revision))
        await asyncio.wait_for(entered.wait(), 2)
        disconnect = asyncio.create_task(rt.disconnect(service.room.revision))
        await asyncio.sleep(0)
        assert service.room.session is None
        release.set()
        with pytest.raises((PurifierUnavailable, ValueError)): await command
        await disconnect
        assert provider.command_count == 0 and service.room.selected is None and service.room.sample is None
    finally: release.set(); await rt.close()


@pytest.mark.asyncio
async def test_pin_privacy_expiry_during_preflight_prevents_transmission(tmp_path):
    provider = Provider()
    service, rt, _, ticks = runtime(tmp_path)
    lock_after_read = [False]
    def handler(request):
        response = provider(request)
        if lock_after_read[0] and request.url.path == BYPASS:
            service.state.pin_unlocked_until = None
            service.phone_disconnected()
        return response
    rt.factory = lambda saved=None, **kwargs: PurifierAdapter(saved, transport=httpx.MockTransport(handler), **kwargs)
    try:
        await connect(rt, ticks)
        service.unlock_with_pin()
        service.update_settings({'onboarding_completed': True})
        lock_after_read[0] = True
        with pytest.raises(RoomAccessChanged): await rt.command('power', False, service.room.revision)
        assert not provider.command_count and service.room.receipt['status'] == 'not_sent'
        assert service.snapshot()['room'] is None
    finally: await rt.close()


@pytest.mark.asyncio
async def test_old_selection_failure_does_not_mark_new_configuration_offline(tmp_path):
    service, rt, provider, ticks = runtime(tmp_path)
    try:
        await connect(rt, ticks)
        revision, generation = service.room.revision, service.room.generation
        service.room.select(None, revision=revision, generation=generation)
        before = (service.room.health, rt.failures, rt.next_poll)
        rt._failed(PurifierReconnect('synthetic'), generation, revision)
        assert (service.room.health, rt.failures, rt.next_poll) == before
        assert not rt.needs_reconnect
    finally: await rt.close()


@pytest.mark.asyncio
async def test_command_discovery_auth_error_sets_reconnect_without_claim(tmp_path):
    service, rt, provider, ticks = runtime(tmp_path)
    try:
        await connect(rt, ticks)
        rt.adapter.devices.clear()
        provider.fail = lambda _: httpx.Response(401)
        with pytest.raises(PurifierReconnect): await rt.command('power', False, service.room.revision)
        assert rt.needs_reconnect and service.room.receipt is None and provider.command_count == 0
    finally: await rt.close()


@pytest.mark.asyncio
async def test_cancel_after_dispatch_leaves_unknown_receipt_and_busy_is_not_queued(tmp_path):
    provider = Provider()
    sent, release = asyncio.Event(), asyncio.Event()
    async def delayed(request):
        response = provider(request)
        if provider.command_count:
            sent.set()
            await release.wait()
        return response
    service, rt, _, ticks = runtime(tmp_path, delayed)
    try:
        await connect(rt, ticks)
        command = asyncio.create_task(rt.command('power', False, service.room.revision))
        await asyncio.wait_for(sent.wait(), 2)
        with pytest.raises(PurifierBusy): await rt.command('power', True, service.room.revision)
        command.cancel()
        with pytest.raises(asyncio.CancelledError): await command
        assert provider.command_count == 1 and service.room.receipt['status'] == 'unconfirmed'
        assert Room(service.storage).receipt['accepted'] is None
    finally: release.set(); await rt.close()


@pytest.mark.asyncio
async def test_receipt_storage_failure_blocks_send_and_preserves_unknown_after_send(tmp_path, monkeypatch):
    service, rt, provider, ticks = runtime(tmp_path)
    try:
        await connect(rt, ticks)
        from contextlib import contextmanager
        original = service.storage.transaction
        @contextmanager
        def fail(): raise OSError('synthetic disk failure'); yield
        monkeypatch.setattr(service.storage, 'transaction', fail)
        with pytest.raises(OSError): await rt.command('power', False, service.room.revision)
        assert provider.command_count == 0 and service.room.receipt is None
        calls = [0]
        @contextmanager
        def fail_finish():
            calls[0] += 1
            if calls[0] > 1: raise OSError('synthetic disk failure')
            with original() as connection: yield connection
        monkeypatch.setattr(service.storage, 'transaction', fail_finish)
        ticks[0] += 5
        with pytest.raises(OSError): await rt.command('power', False, service.room.revision)
        assert provider.command_count == 1 and service.room.receipt['status'] == 'unconfirmed'
        assert Room(service.storage).receipt['status'] == 'unconfirmed'
    finally: await rt.close()


def test_room_configuration_owner_gate_and_secret_body_never_echoed(tmp_path):
    app = create_app(data_dir=tmp_path)
    service = app.state.luma
    service.display_clock_trusted = lambda: True
    client = TestClient(app, client=('127.0.0.1', 50000))
    config = client.get('/api/v1/room').json()
    for body in ('{"username":"SECRET_ECHO","username":"duplicate"}', json.dumps({'password': 'SECRET_ECHO'}), 'x' * 4097):
        response = client.post('/api/v1/room/vesync/login', content=body)
        assert response.status_code == 422 and 'SECRET_ECHO' not in response.text
    service.update_settings({'onboarding_completed': True})
    assert client.get('/api/v1/room').status_code == 403
    assert client.post('/api/v1/room/purifier/discover', json={'revision': config['revision']}).status_code == 403
    service.unlock_with_pin()
    assert client.get('/api/v1/room').status_code == 200
    assert client.get('/api/v1/room', headers={'origin': 'https://evil.invalid'}).status_code == 403
    remote = TestClient(app, client=('192.0.2.25', 50000))
    assert remote.get('/api/v1/room').status_code == 403


def test_room_pin_does_not_bypass_untrusted_system_clock(tmp_path):
    app = create_app(data_dir=tmp_path)
    service = app.state.luma
    service.display_clock_trusted = lambda: False
    service.update_settings({'onboarding_completed': True})
    service.unlock_with_pin()
    client = TestClient(app, client=('127.0.0.1', 50000))
    assert client.get('/api/v1/room').status_code == 403
    assert client.post('/api/v1/room/purifier/command', json={
        'revision': service.room.revision, 'action': 'power', 'value': True,
    }).status_code == 403
    assert service.room.receipt is None


def test_api_real_library_synthetic_login_discovery_selection_command(tmp_path):
    app = create_app(data_dir=tmp_path)
    provider = Provider()
    rt = app.state.room_runtime
    ticks = [1000.0]
    rt.clock = lambda: ticks[0]
    rt.factory = lambda saved=None, **kwargs: PurifierAdapter(saved, transport=httpx.MockTransport(provider), **kwargs)
    # No lifespan: no unrelated cloud/audio/radio workers in this test.
    client = TestClient(app, client=('127.0.0.1', 50000))
    try:
        config = client.get('/api/v1/room').json()
        response = client.post('/api/v1/room/vesync/login', json={'username': 'QA_EMAIL', 'password': 'QA_PASSWORD', 'country': 'US', 'revision': config['revision']})
        assert response.status_code == 200
        assert all(value not in response.text for value in ('QA_EMAIL', 'QA_PASSWORD', SECRET['token'], SECRET['account_id']))
        config = response.json()
        assert config['connected'] and config['selected'] is None and not config['remote_control']
        ticks[0] += 5
        discovery = client.post('/api/v1/room/purifier/discover', json={'revision': config['revision']}).json()
        response = client.post('/api/v1/room/purifier/select', json={'revision': config['revision'], 'device_id': discovery['devices'][0]['id'], 'name': 'QA selected'})
        assert response.status_code == 200
        config = response.json()
        ticks[0] += 5
        response = client.post('/api/v1/room/purifier/command', json={'revision': config['revision'], 'action': 'power', 'value': False})
        assert response.status_code == 200 and response.json()['result']['status'] == 'confirmed'
        assert provider.command_count == 1
        response = client.post('/api/v1/room/vesync/disconnect', json={'revision': config['revision']})
        assert response.status_code == 200 and not response.json()['connected'] and response.json()['selected'] is None
    finally:
        asyncio.run(rt.close())
