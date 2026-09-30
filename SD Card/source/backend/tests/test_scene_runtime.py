import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import sys
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from luma.api import create_app
from luma.models import CalendarEvent
from luma.scene_presence import ScenePresence, evidence
from luma.scene_runtime import SceneRuntime, sleep_interval
from luma.scene_triggers import SceneTrigger
from luma.service import LumaService
from luma.storage import Storage
from test_scenes import CONFIG, NOW

ADDRESS = 'AA:BB:CC:DD:EE:FF'
OBJECTS = {'/adapter': {'org.bluez.Adapter1': {'Powered': True}}, '/phone': {'org.bluez.Device1': {
    'Adapter': '/adapter', 'Address': ADDRESS, 'Paired': True, 'Bonded': True, 'Trusted': True,
    'Connected': True, 'ServicesResolved': True,
}}}


def test_radio_evidence_requires_power_bond_trust_and_authorized_session():
    assert evidence(OBJECTS, ADDRESS, authorized=True) is True
    assert evidence(OBJECTS, ADDRESS, authorized=False) is None
    for key in ('Paired', 'Bonded', 'Trusted', 'ServicesResolved'):
        objects = deepcopy(OBJECTS); objects['/phone']['org.bluez.Device1'][key] = False
        assert evidence(objects, ADDRESS, authorized=True) is None
    objects = deepcopy(OBJECTS); objects['/phone']['org.bluez.Device1']['Connected'] = False
    assert evidence(objects, ADDRESS, authorized=False) is False
    objects['/adapter']['org.bluez.Adapter1']['Powered'] = False
    assert evidence(objects, ADDRESS, authorized=False) is None
    assert evidence({}, ADDRESS, authorized=True) is None


def test_presence_evidence_expires_and_never_crosses_pairing_identity():
    ticks = [0]
    evidence_store = ScenePresence(clock=lambda: ticks[0])
    evidence_store.update(ADDRESS, True)
    assert evidence_store.read(ADDRESS) is True
    assert evidence_store.read('other') is None
    ticks[0] = 6
    assert evidence_store.read(ADDRESS) is None
    evidence_store.update(ADDRESS, None)
    assert evidence_store.sample is None


def runtime(tmp_path):
    service = LumaService(Storage(tmp_path / 'scenes.db'), clock_trusted=lambda: True)
    service.update_settings({'onboarding_completed': True, 'phone_address': ADDRESS, 'sleep_calendar_ids': ['sleep']})
    ticks = [0]
    bluetooth = SimpleNamespace(scene_presence=ScenePresence(clock=lambda: ticks[0]))
    room = SimpleNamespace()
    rt = SceneRuntime(service, room, bluetooth, clock=lambda: ticks[0], utcnow=lambda: NOW + timedelta(seconds=ticks[0]))
    dispatch = AsyncMock(return_value='confirmed')
    rt.executor.dispatch = dispatch
    return service, rt, ticks, dispatch


def configure_scene(service, key):
    service.scenes.edit(key, CONFIG, revision=service.scenes.revision)


@pytest.mark.asyncio
async def test_disabled_and_boot_presence_never_trigger_then_true_arrival_runs_once(tmp_path):
    service, rt, ticks, dispatch = runtime(tmp_path)
    configure_scene(service, 'arrive')
    for second in range(40):
        ticks[0] = second; rt.bluetooth.scene_presence.update(ADDRESS, True); rt.poll()
    assert not dispatch.called and not service.scenes.runs
    # Establish known departure for the full debounce even though Away is off.
    for second in range(40, 230):
        ticks[0] = second; rt.bluetooth.scene_presence.update(ADDRESS, False); rt.poll()
    assert not dispatch.called
    for second in range(230, 261):
        ticks[0] = second; rt.bluetooth.scene_presence.update(ADDRESS, True); rt.poll()
    await rt.job
    assert dispatch.await_count == 1 and service.scenes.runs[-1]['source'] == 'presence'
    await rt.close()


@pytest.mark.asyncio
async def test_radio_uncertainty_is_not_away_and_manual_privacy_cannot_forge_presence(tmp_path):
    service, rt, ticks, dispatch = runtime(tmp_path)
    configure_scene(service, 'away')
    rt.bluetooth.scene_presence.update(ADDRESS, True); rt.poll()
    service.phone_disconnected(); service.unlock_with_pin()
    for second in range(1, 200):
        ticks[0] = second; rt.bluetooth.scene_presence.update(ADDRESS, None); rt.poll()
    assert not dispatch.called
    forged = SceneTrigger('away', 'presence', 'invented', NOW)
    assert not rt.authorize(forged)
    await rt.close()


@pytest.mark.asyncio
async def test_known_disconnection_runs_away_after_three_minutes_even_private(tmp_path):
    service, rt, ticks, dispatch = runtime(tmp_path)
    configure_scene(service, 'away')
    rt.bluetooth.scene_presence.update(ADDRESS, True); rt.poll()
    for second in range(1, 182):
        ticks[0] = second; rt.bluetooth.scene_presence.update(ADDRESS, False); rt.poll()
    await rt.job
    assert dispatch.await_count == 1 and service.scenes.runs[-1]['scene'] == 'away'
    await rt.close()


@pytest.mark.asyncio
async def test_actual_selected_sleep_crossings_run_and_stale_cache_never_replays(tmp_path):
    service, rt, ticks, dispatch = runtime(tmp_path)
    configure_scene(service, 'night'); configure_scene(service, 'morning')
    service.events = [CalendarEvent('sleep-event', 'sleep', 'Sleep', NOW + timedelta(seconds=2), NOW + timedelta(seconds=6))]
    service.calendar_synced_at = NOW
    for second in range(3): ticks[0] = second; rt.poll()
    await rt.job
    assert service.scenes.runs[-1]['scene'] == 'night'
    for second in range(3, 7): ticks[0] = second; rt.poll()
    await rt.job
    assert service.scenes.runs[-1]['scene'] == 'morning' and dispatch.await_count == 2
    service.calendar_sync_error = True
    for second in range(7, 15): ticks[0] = second; rt.poll()
    service.calendar_sync_error = False
    ticks[0] = 15; rt.poll()
    assert dispatch.await_count == 2
    await rt.close()


def test_merged_sleep_selection_ignores_wrong_calendar_cancelled_and_declined(tmp_path):
    service, rt, ticks, _ = runtime(tmp_path)
    service.events = [CalendarEvent('a', 'sleep', 'Sleep', NOW - timedelta(hours=2), NOW + timedelta(hours=1)),
                      CalendarEvent('b', 'sleep', 'Sleep', NOW + timedelta(hours=1), NOW + timedelta(hours=2)),
                      CalendarEvent('c', 'other', 'Sleep', NOW, NOW + timedelta(hours=9)),
                      CalendarEvent('d', 'sleep', 'Sleep', NOW, NOW + timedelta(hours=9), self_declined=True)]
    assert sleep_interval(service, NOW) == (NOW - timedelta(hours=2), NOW + timedelta(hours=2))


def test_fastapi_lifespan_syncs_selected_sleep_calendar_and_runs_night_scene(tmp_path):
    """Exercise production worker startup with synthetic Google/device boundaries."""
    app = create_app(data_dir=tmp_path)
    service = app.state.luma
    service.display_clock_trusted = lambda: True
    service.update_settings({'onboarding_completed': True,
                             'visible_calendar_ids': ['agenda'],
                             'sleep_calendar_ids': ['sleep-selected']})
    service.scenes.edit('night', deepcopy(CONFIG), revision=service.scenes.revision)

    requested = []
    fetched_events = []
    app.state.google.authorized = lambda: True

    def fetch_events(calendar_ids, start, end, timezone):
        requested.append(list(calendar_ids))
        now = datetime.now(UTC)
        event = CalendarEvent('sleep-event', 'sleep-selected', 'Sleep',
                              now + timedelta(seconds=6), now + timedelta(seconds=22))
        fetched_events.append(event)
        return [event]

    app.state.google.fetch_events = fetch_events
    dispatched = Event()

    async def dispatch(*_args, **_kwargs):
        dispatched.set()
        return 'confirmed'

    app.state.scene_runtime.executor.dispatch = dispatch
    client = TestClient(app, client=('127.0.0.1', 1234))
    with client:
        deadline = monotonic() + 14
        while not requested and monotonic() < deadline:
            sleep(.02)
        assert requested and requested[0] == ['agenda', 'sleep-selected']
        assert dispatched.wait(max(0, deadline - monotonic())), 'selected Sleep boundary did not dispatch'

    assert [row['scene'] for row in service.scenes.runs] == ['night']
    assert service.scenes.runs[0]['source'] == 'calendar'
    assert service.events == fetched_events


def test_fastapi_lifespan_bluez_presence_requires_fresh_authorized_phone_session(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path)
    service = app.state.luma
    service.display_clock_trusted = lambda: True
    service.update_settings({'onboarding_completed': True, 'phone_address': ADDRESS})
    service.scenes.edit('arrive', deepcopy(CONFIG), revision=service.scenes.revision)
    bluetooth = app.state.scene_runtime.bluetooth
    bluetooth.scene_authorized = None

    class Variant:
        def __init__(self, value): self.value = value

    properties = {'Adapter': '/adapter', 'Address': ADDRESS, 'Paired': True, 'Bonded': True,
                  'Trusted': True, 'Connected': True, 'ServicesResolved': True}
    managed_objects = {
        '/adapter': {'org.bluez.Adapter1': {'Powered': Variant(True)}},
        '/phone': {'org.bluez.Device1': {key: Variant(value) for key, value in properties.items()}},
    }
    radio_polled = Event()

    class Manager:
        async def call_get_managed_objects(self):
            radio_polled.set()
            return managed_objects

    class Proxy:
        def get_interface(self, _name): return Manager()

    class Bus:
        async def connect(self): return self
        async def introspect(self, _service, _path): return object()
        def get_proxy_object(self, _service, _path, _intro): return Proxy()
        def disconnect(self): pass

    fake_dbus = SimpleNamespace(BusType=SimpleNamespace(SYSTEM=object()))
    fake_dbus_aio = SimpleNamespace(MessageBus=lambda *, bus_type: Bus())
    monkeypatch.setitem(sys.modules, 'dbus_next', fake_dbus)
    monkeypatch.setitem(sys.modules, 'dbus_next.aio', fake_dbus_aio)
    import luma.bluetooth_runtime as bluetooth_module
    monkeypatch.setattr(bluetooth_module, 'sys', SimpleNamespace(platform='linux'))

    async def idle_radio_session():
        await asyncio.Event().wait()

    bluetooth.run = idle_radio_session
    client = TestClient(app, client=('127.0.0.1', 1234))
    with client:
        deadline = monotonic() + 7
        assert radio_polled.wait(max(0, deadline - monotonic()))
        # A connected/paird device without the ANCS-authorized session is unknown.
        assert bluetooth.scene_presence.read(ADDRESS) is None
        bluetooth.scene_authorized = (ADDRESS, monotonic())
        while monotonic() < deadline and bluetooth.scene_presence.read(ADDRESS) is not True:
            sleep(.02)
        assert bluetooth.scene_presence.read(ADDRESS) is True
        assert not service.scenes.runs  # startup presence is only a baseline, never Arrive


def test_scene_api_local_owner_strict_body_no_remote_raw_trigger(tmp_path):
    app = create_app(data_dir=tmp_path)
    service = app.state.luma
    service.display_clock_trusted = lambda: True
    client = TestClient(app, client=('127.0.0.1', 1234))
    response = client.get('/api/v1/scenes')
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    revision = response.json()['revision']
    for body in ('x' * 8193, '{"revision":"x","revision":"y"}', '{}'):
        assert client.put('/api/v1/scenes/night', content=body).status_code == 422
    assert client.post('/api/v1/scenes/night/run', json={'revision': revision, 'source': 'presence'}).status_code == 422
    assert client.put('/api/v1/scenes/night', json={'revision': revision, **CONFIG}).status_code == 409
    assert client.get('/api/v1/scenes', headers={'origin': 'https://evil.invalid'}).status_code == 403
    remote = TestClient(app, client=('192.0.2.10', 1234))
    assert remote.get('/api/v1/scenes').status_code == 403
    service.update_settings({'onboarding_completed': True})
    assert client.get('/api/v1/scenes').status_code == 403
    service.unlock_with_pin()
    assert client.get('/api/v1/scenes').status_code == 200


@pytest.mark.asyncio
async def test_scene_runtime_cancel_covers_voice_acknowledgement_before_claim(tmp_path):
    service=LumaService(Storage(tmp_path/'luma.db'),clock_trusted=lambda:True)
    service.display_clock_trusted=lambda:True
    runtime=SceneRuntime(service,AsyncMock(),SimpleNamespace(scene_presence=SimpleNamespace(read=lambda _:None)))
    attempted=[]
    async def queued_manual():
        attempted.append(True)
        await runtime.manual('morning',runtime.store.revision)
    pending=asyncio.create_task(queued_manual())
    runtime.job=pending
    await runtime.cancel()
    assert pending.cancelled() and attempted==[] and runtime.store.runs==[]
