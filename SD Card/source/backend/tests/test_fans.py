import asyncio
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
import pytest

from luma.api import create_app
from luma.fans import Fans, BUTTONS, basis
from luma.fan_runtime import FanRuntime, FanAccessChanged, FanCancelled
from luma.ir_protocol import InfraredBusy, InfraredError, InfraredUnavailable, send_result
from luma.service import LumaService
from luma.storage import Storage

NOW = datetime(2026, 9, 26, 21, tzinfo=UTC)
DEVICE = {'id': 'usb-ir-' + 'a' * 24, 'name': 'USB IR', 'serial_present': True, 'send': True,
          'receive': True, 'measure_carrier': True, 'emitter_selection': True}
RAW = {'carrier_hz': 38000, 'durations': [9000, 4500, 560, 560, 560, 560, 560]}


def configure(store, *, serial=True):
    for index, fan in enumerate(('fan_1', 'fan_2')):
        store.select(fan, f'Fan {index + 1}', {'device': {**DEVICE, 'serial_present': serial}, 'emitter': index + 1},
                     revision=store.revision, generation=store.generation)
    for fan in ('fan_1', 'fan_2'):
        store.learned(fan, 'power_off', RAW, revision=store.revision, generation=store.generation)
    return store


def observed(store, fan='fan_1', key='power_off', now=NOW, good=True):
    identifier, payload = store.claim(fan, key, kind='test', confirmed=True, revision=store.revision, generation=store.generation, now=now)
    store.finish(fan, identifier, 'sent_unconfirmed', revision=store.revision, generation=store.generation)
    store.observe(fan, identifier, good, good, revision=store.revision, generation=store.generation, now=now, repeat_same_state=True)
    return identifier, payload


def test_saved_routes_buttons_and_proofs_survive_without_replay_or_raw_public_data(tmp_path):
    store = configure(Fans(Storage(tmp_path / 'test.db')))
    observed(store)
    observed(store, 'fan_2')
    restored = Fans(store.storage)
    assert restored.slots == store.slots and restored.revision == store.revision
    assert restored.generation != store.generation and restored.independent()
    view = json.dumps(restored.configuration(NOW))
    assert 'durations' not in view and 'carrier_hz' not in view
    assert restored.configuration(NOW)['remote_control'] is False
    assert not restored.configuration(NOW)['fans'][0]['buttons'][0]['scene_eligible']


def test_route_changes_clear_both_directions_but_names_do_not(tmp_path):
    store = configure(Fans(Storage(tmp_path / 'test.db')))
    observed(store); observed(store, 'fan_2')
    row = store.slots['fan_1']
    store.select('fan_1', 'Desk fan', row['route'], revision=store.revision, generation=store.generation)
    assert store.independent()
    store.select('fan_1', 'Desk fan', {**row['route'], 'emitter': 3}, revision=store.revision, generation=store.generation)
    assert not store.independent()
    assert not store.slots['fan_1']['buttons']
    assert store.slots['fan_2']['buttons']['power_off']['checks'] == 0


def test_relearning_only_invalidates_that_button_and_old_observations(tmp_path):
    store = configure(Fans(Storage(tmp_path / 'test.db')))
    old, _ = observed(store)
    observed(store, 'fan_2')
    store.learned('fan_1', 'power_off', {**RAW, 'carrier_hz': 40000}, revision=store.revision, generation=store.generation)
    assert store.slots['fan_1']['buttons']['power_off']['checks'] == 0
    assert store.slots['fan_2']['buttons']['power_off']['checks'] == 1
    with pytest.raises(ValueError): store.observe('fan_1', old, True, True, revision=store.revision, generation=store.generation, now=NOW)


def test_scene_requires_repeatable_absolute_both_directions_and_expired_override(tmp_path):
    store = configure(Fans(Storage(tmp_path / 'test.db')))
    observed(store); observed(store)
    with pytest.raises(ValueError): store.command('fan_1', 'power_off', kind='scene', confirmed=False, now=NOW + timedelta(hours=2))
    observed(store, 'fan_2')
    with pytest.raises(ValueError, match='override'): store.command('fan_1', 'power_off', kind='scene', confirmed=False, now=NOW)
    assert store.command('fan_1', 'power_off', kind='scene', confirmed=False, now=NOW + timedelta(hours=2))['emitter'] == 1
    store.learned('fan_1', 'power_toggle', RAW, revision=store.revision, generation=store.generation)
    observed(store, key='power_toggle'); observed(store, key='power_toggle')
    with pytest.raises(ValueError, match='absolute'): store.command('fan_1', 'power_toggle', kind='scene', confirmed=True, now=NOW + timedelta(hours=2))
    with pytest.raises(ValueError, match='Confirm'): store.command('fan_1', 'power_toggle', kind='manual', confirmed=False, now=NOW)


def test_second_absolute_check_requires_explicit_same_state_observation(tmp_path):
    store = configure(Fans(Storage(tmp_path / 'test.db')))
    observed(store)
    identifier, _ = store.claim('fan_1', 'power_off', kind='test', confirmed=True, revision=store.revision, generation=store.generation, now=NOW)
    store.finish('fan_1', identifier, 'sent_unconfirmed', revision=store.revision, generation=store.generation)
    with pytest.raises(ValueError, match='already'):
        store.observe('fan_1', identifier, True, True, revision=store.revision, generation=store.generation, now=NOW)
    assert store.slots['fan_1']['buttons']['power_off']['checks'] == 1
    store.observe('fan_1', identifier, True, True, revision=store.revision, generation=store.generation, now=NOW, repeat_same_state=True)
    assert store.slots['fan_1']['buttons']['power_off']['checks'] == 2


def test_one_observation_cannot_be_reused_for_two_checks_and_failures_revoke_proofs(tmp_path):
    store = configure(Fans(Storage(tmp_path / 'test.db')))
    identifier, _ = observed(store)
    with pytest.raises(ValueError): store.observe('fan_1', identifier, True, True, revision=store.revision, generation=store.generation, now=NOW)
    observed(store, 'fan_2')
    observed(store, good=False)
    assert not store.independent()
    assert all(not item['checks'] for row in store.slots.values() for item in row['buttons'].values())


@pytest.mark.parametrize('status,age', [('unknown', 0), ('not_sent', 0), ('sent_unconfirmed', 121), ('sent_unconfirmed', -1)])
def test_unknown_late_or_clock_reversed_test_cannot_be_confirmed(tmp_path, status, age):
    store = configure(Fans(Storage(tmp_path / 'test.db')))
    identifier, _ = store.claim('fan_1', 'power_off', kind='test', confirmed=True, revision=store.revision, generation=store.generation, now=NOW)
    store.finish('fan_1', identifier, status, revision=store.revision, generation=store.generation)
    with pytest.raises(ValueError): store.observe('fan_1', identifier, True, True, revision=store.revision, generation=store.generation, now=NOW + timedelta(seconds=age))


def test_interrupted_command_and_override_survive_restart_and_selection_edit(tmp_path):
    store = configure(Fans(Storage(tmp_path / 'test.db')))
    identifier, _ = store.claim('fan_1', 'power_off', kind='test', confirmed=True, revision=store.revision, generation=store.generation, now=NOW)
    restored = Fans(store.storage)
    assert restored.receipts['fan_1']['id'] == identifier and restored.receipts['fan_1']['status'] == 'unknown'
    restored.select('fan_1', None, None, revision=restored.revision, generation=restored.generation)
    assert instant_override(restored) == NOW + timedelta(hours=1)
    assert not restored.finish('fan_1', identifier, 'sent_unconfirmed', revision=store.revision, generation=store.generation)


def instant_override(store): return datetime.fromisoformat(store.overrides['fan_1'])


def test_failed_storage_claim_does_not_change_live_state(tmp_path, monkeypatch):
    store = configure(Fans(Storage(tmp_path / 'test.db')))
    before = store.configuration(NOW)
    @contextmanager
    def failed(): raise OSError('disk full'); yield
    monkeypatch.setattr(store.storage, 'transaction', failed)
    with pytest.raises(OSError): store.claim('fan_1', 'power_off', kind='test', confirmed=True, revision=store.revision, generation=store.generation, now=NOW)
    assert store.configuration(NOW) == before


@pytest.mark.parametrize('bad', [[], {'version': 99}, {'version': True}])
def test_corrupt_saved_record_preserved_and_disabled(tmp_path, bad):
    storage = Storage(tmp_path / 'test.db')
    storage.set_cache('room', 'fans', bad)
    store = Fans(storage)
    assert store.recovery_error
    with pytest.raises(ValueError, match='recovery'): configure(store)
    assert storage.get_cache('room', 'fans') == bad


def test_changed_saved_signal_cannot_reuse_proof(tmp_path):
    storage = Storage(tmp_path / 'test.db')
    store = configure(Fans(storage)); observed(store)
    raw = storage.get_cache('room', 'fans')
    raw['slots']['fan_1']['buttons']['power_off']['signal']['carrier_hz'] = 40000
    storage.set_cache('room', 'fans', raw)
    assert Fans(storage).recovery_error
    assert storage.get_cache('room', 'fans') == raw


class Transport:
    def __init__(self): self.calls = []; self.gate = None; self.started = asyncio.Event(); self.cancelled = False; self.status = 'sent_unconfirmed'
    async def __call__(self, payload):
        self.calls.append(deepcopy(payload))
        if self.gate is not None:
            self.started.set()
            try: await self.gate.wait()
            except asyncio.CancelledError: self.cancelled = True; raise
        if payload['action'] == 'discover': return {'devices': [DEVICE]}
        if payload['action'] == 'learn': return {'signal': {**RAW, 'carrier_source': 'measured'}}
        return send_result(self.status)


def runtime(tmp_path, *, configured=True):
    store = Fans(Storage(tmp_path / 'test.db'))
    if configured: configure(store)
    service = SimpleNamespace(fans=store, settings=SimpleNamespace(onboarding_completed=True), locked=False, events=[])
    service.snapshot = lambda: {'privacy_redacted': service.locked}
    service.publish = service.events.append
    transport = Transport()
    tick = [100.0]
    run = FanRuntime(service, transport=transport, clock=lambda: tick[0], utcnow=lambda: NOW)
    return run, service, transport, tick


@pytest.mark.asyncio
async def test_runtime_discover_select_learn_restart_and_no_idle_network(tmp_path):
    run, service, transport, tick = runtime(tmp_path, configured=False)
    assert not transport.calls
    await run.discover(run.store.revision); tick[0] += 2
    await run.select('fan_1', DEVICE['id'], 1, 'Desk fan', run.store.revision); tick[0] += 2
    await run.learn('fan_1', 'power_off', DEVICE['id'], None, run.store.revision)
    assert [call['action'] for call in transport.calls] == ['discover', 'learn']
    assert Fans(run.store.storage).slots['fan_1']['buttons']['power_off']['signal'] == RAW
    assert 'durations' not in json.dumps(run.configuration())


@pytest.mark.asyncio
async def test_privacy_revokes_inflight_learning_and_does_not_save(tmp_path):
    run, service, transport, tick = runtime(tmp_path)
    await run.discover(run.store.revision); tick[0] += 2
    transport.gate = asyncio.Event()
    task = asyncio.create_task(run.learn('fan_1', 'power_on', DEVICE['id'], None, run.store.revision))
    await transport.started.wait()
    service.locked = True
    with pytest.raises(FanAccessChanged): await asyncio.wait_for(task, 1)
    assert transport.cancelled and 'power_on' not in run.store.slots['fan_1']['buttons']


@pytest.mark.asyncio
async def test_explicit_cancel_discards_learning_without_changing_existing_buttons(tmp_path):
    run, service, transport, tick = runtime(tmp_path)
    await run.discover(run.store.revision); tick[0] += 2
    before = deepcopy(run.store.slots)
    transport.gate = asyncio.Event()
    task = asyncio.create_task(run.learn('fan_1', 'power_off', DEVICE['id'], None, run.store.revision))
    await transport.started.wait()
    await run.cancel()
    with pytest.raises(FanCancelled): await task
    assert transport.cancelled and run.store.slots == before


@pytest.mark.asyncio
async def test_remove_invalidates_inflight_learn_and_busy_never_queues(tmp_path):
    run, service, transport, tick = runtime(tmp_path)
    await run.discover(run.store.revision); tick[0] += 2
    transport.gate = asyncio.Event()
    task = asyncio.create_task(run.learn('fan_1', 'power_off', DEVICE['id'], None, run.store.revision))
    await transport.started.wait()
    with pytest.raises(InfraredBusy): await run.command('fan_2', 'power_off', run.store.revision, test=True, confirmed=True)
    await run.remove('fan_1', run.store.revision)
    with pytest.raises((FanCancelled, ValueError)): await task
    assert run.store.slots['fan_1'] is None and transport.cancelled
    assert len(transport.calls) == 2


@pytest.mark.asyncio
async def test_receipt_precedes_transmit_and_cancellation_keeps_unknown(tmp_path):
    run, service, transport, tick = runtime(tmp_path)
    transport.gate = asyncio.Event()
    task = asyncio.create_task(run.command('fan_1', 'power_off', run.store.revision, test=True, confirmed=True))
    await transport.started.wait()
    restored = Fans(run.store.storage)
    assert restored.receipts['fan_1']['status'] == 'unknown'
    await run.cancel()
    with pytest.raises(FanCancelled): await task
    assert run.store.receipts['fan_1']['status'] == 'unknown' and len(transport.calls) == 1


@pytest.mark.asyncio
async def test_disk_error_before_dispatch_sends_nothing(tmp_path, monkeypatch):
    run, service, transport, tick = runtime(tmp_path)
    def failed(*args, **kwargs): raise OSError('disk full')
    monkeypatch.setattr(run.store.storage, 'set_cache', failed)
    with pytest.raises(OSError): await run.command('fan_1', 'power_off', run.store.revision, test=True, confirmed=True)
    assert not transport.calls


@pytest.mark.asyncio
async def test_unknown_send_never_observable_or_retried(tmp_path):
    run, service, transport, tick = runtime(tmp_path)
    transport.status = 'unknown'
    result = await run.command('fan_1', 'power_off', run.store.revision, test=True, confirmed=True)
    assert result['status'] == 'unknown' and len(transport.calls) == 1
    tick[0] += 2
    with pytest.raises(ValueError): await run.observe('fan_1', result['id'], True, True, run.store.revision)


@pytest.mark.asyncio
async def test_no_serial_output_requires_boot_local_review(tmp_path):
    run, service, transport, tick = runtime(tmp_path)
    configure(run.store, serial=False)
    assert all(row['needs_output_review'] for row in run.configuration()['fans'])
    transport_result = {**DEVICE, 'serial_present': False}
    run.transport = AsyncMock(return_value={'devices': [transport_result]})
    await run.discover(run.store.revision); tick[0] += 2
    await run.review_output('fan_1', run.store.revision)
    assert not run.configuration()['fans'][0]['needs_output_review']
    assert run.configuration()['fans'][1]['needs_output_review']
    assert FanRuntime(service).configuration()['fans'][0]['needs_output_review']


def api(tmp_path):
    app = create_app(data_dir=tmp_path)
    configure(app.state.luma.fans)
    app.state.fan_runtime.transport = Transport()
    app.state.fan_runtime.utcnow = lambda: NOW
    return app, TestClient(app, client=('127.0.0.1', 40100))


def test_api_local_owner_only_no_raw_ir_and_safe_results(tmp_path):
    app, client = api(tmp_path)
    revision = app.state.luma.fans.revision
    state = client.get('/api/v1/fans')
    assert state.status_code == 200 and state.headers['cache-control'] == 'no-store'
    assert 'durations' not in state.text
    body = {'revision': revision, 'fan': 'fan_1', 'button': 'power_off', 'confirmed': True}
    assert client.post('/api/v1/fans/test', json={**body, 'signal': RAW}).status_code == 422
    assert client.post('/api/v1/fans/test', json={**body, 'confirmed': 1}).status_code == 422
    result = client.post('/api/v1/fans/test', json=body)
    assert result.status_code == 200 and result.json()['result']['status'] == 'sent_unconfirmed'
    assert 'durations' not in result.text
    assert client.post('/api/v1/fans/discover', json={'revision': revision}, headers={'Origin': 'https://evil.example'}).status_code == 403
    remote = TestClient(app, client=('192.0.2.1', 9000))
    assert remote.get('/api/v1/fans').status_code == 403
    app.state.luma.settings.onboarding_completed = True
    assert app.state.luma.snapshot()['privacy_redacted']
    assert client.get('/api/v1/fans').status_code == 403
    assert client.post('/api/v1/fans/test', json=body).status_code == 403
    assert len(app.state.fan_runtime.transport.calls) == 1


def test_api_missing_transport_explicit_error_and_no_fake_success(tmp_path):
    app, client = api(tmp_path)
    app.state.fan_runtime.transport = AsyncMock(side_effect=InfraredUnavailable('host detail'))
    result = client.post('/api/v1/fans/discover', json={'revision': app.state.luma.fans.revision})
    assert result.status_code == 503 and 'host detail' not in result.text


@pytest.mark.asyncio
async def test_asgi_disconnect_cancels_capture_before_late_save(tmp_path):
    app = create_app(data_dir=tmp_path)
    store = configure(app.state.luma.fans)
    rt = app.state.fan_runtime
    transport = Transport()
    transport.gate = asyncio.Event()
    rt.transport = transport
    rt.catalog, rt.catalog_at = [DEVICE], rt.clock()
    incoming, outgoing = asyncio.Queue(), []
    body = json.dumps({'revision': store.revision, 'fan': 'fan_1', 'button': 'power_on',
                       'receiver_id': DEVICE['id'], 'carrier_hz': None}).encode()
    await incoming.put({'type': 'http.request', 'body': body, 'more_body': False})
    scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': 'POST',
             'scheme': 'http', 'path': '/api/v1/fans/learn', 'raw_path': b'/api/v1/fans/learn',
             'query_string': b'', 'root_path': '', 'headers': [(b'host', b'localhost'), (b'content-type', b'application/json')],
             'client': ('127.0.0.1', 50500), 'server': ('127.0.0.1', 8750)}
    async def send(message): outgoing.append(message)
    task = asyncio.create_task(app(scope, incoming.get, send))
    await asyncio.wait_for(transport.started.wait(), 1)
    await incoming.put({'type': 'http.disconnect'})
    await asyncio.wait_for(task, 2)
    assert transport.cancelled and 'power_on' not in store.slots['fan_1']['buttons']
    assert not rt.lock.locked() and rt.io_task is None


@pytest.mark.asyncio
async def test_output_selection_rejects_stale_catalog_and_unknown_adapter(tmp_path):
    rt, service, transport, tick = runtime(tmp_path)
    await rt.discover(rt.store.revision); tick[0] += 301
    with pytest.raises(ValueError, match='Discover'): await rt.select('fan_1', DEVICE['id'], 1, 'New', rt.store.revision)
    tick[0] += 2
    rt.catalog_at = tick[0]
    with pytest.raises(ValueError, match='compatible'): await rt.select('fan_1', 'usb-ir-' + 'b' * 24, 1, 'New', rt.store.revision)
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_failed_final_receipt_write_leaves_durable_unknown_no_second_send(tmp_path, monkeypatch):
    rt, service, transport, tick = runtime(tmp_path)
    original = rt.store.storage.set_cache
    calls = [0]
    def save(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 2: raise OSError('disk full after send')
        return original(*args, **kwargs)
    monkeypatch.setattr(rt.store.storage, 'set_cache', save)
    with pytest.raises(OSError): await rt.command('fan_1', 'power_off', rt.store.revision, test=True, confirmed=True)
    assert len(transport.calls) == 1
    assert Fans(rt.store.storage).receipts['fan_1']['status'] == 'unknown'


@pytest.mark.asyncio
async def test_shutdown_revokes_capture_and_future_operations(tmp_path):
    rt, service, transport, tick = runtime(tmp_path)
    await rt.discover(rt.store.revision); tick[0] += 2
    transport.gate = asyncio.Event()
    task = asyncio.create_task(rt.learn('fan_1', 'power_on', DEVICE['id'], None, rt.store.revision))
    await transport.started.wait()
    await rt.close()
    with pytest.raises((FanAccessChanged, asyncio.CancelledError)): await task
    assert transport.cancelled and not rt.owner_allowed()
