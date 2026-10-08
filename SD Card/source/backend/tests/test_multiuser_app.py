"""Live app controllers with synthetic ANCS authorization, not Pi acceptance."""
from datetime import UTC, datetime, timedelta
from itertools import product
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from luma.api import create_app
from luma.integrations.google_calendar import TOKEN_KEY
from luma.models import CalendarEvent, PhoneNotification
from luma.multi_bluetooth import MultiPhoneBluetooth


@pytest.fixture
def app_rig(tmp_path):
    app = create_app(data_dir=tmp_path)
    service, profiles = app.state.luma, app.state.profiles
    service.display_clock_trusted = lambda: True
    now = datetime.now(UTC)
    users = [profiles.get('primary')] + [profiles.create_secondary(f'Guest {number}') for number in range(4)]
    for index, user in enumerate(users):
        profiles.bind_phone(user.id, f'AA:BB:CC:DD:EE:{index+1:02X}')
        profiles.set_setup(user.id, 'ready', wall_share_approved=True)
        profiles.update_personal(user.id, {'visible_calendar_ids': ['events'], 'todo_calendar_id': 'tasks'})
        account = app.state.profile_calendars.account(user.id)
        account.events = [CalendarEvent('event', 'events', user.nickname+' PRIVATE', now, now+timedelta(hours=1))]
        account.status['last_synced'] = now.isoformat()
        account.google.authorized = Mock(return_value=True)
    service.machine.settings = profiles.storage.load_settings()
    service.replace_events(app.state.profile_calendars.account('primary').events, now)
    def link(uid):
        user = profiles.get(uid)
        child = app.state.bluetooth.runtime(uid)
        child.remote_authorized.begin(user.phone_address, '/phone-'+uid, '/source-'+uid)
        child.remote_authorized.heartbeat(user.phone_address)
        child.service.phone_seen(now)
    return app, users, link, now


@pytest.mark.parametrize('combination', list(product([False, True], repeat=5)))
def test_live_app_all_presence_combinations_keep_primary_flat_fields_isolated(app_rig, combination):
    app, users, link, now = app_rig
    assert isinstance(app.state.bluetooth, MultiPhoneBluetooth)
    active = {user.id for user, enabled in zip(users, combination) if enabled}
    for uid in active:
        link(uid)
    view = app.state.luma.snapshot(now)
    assert {row['profile_id'] for row in view['users']} == active
    assert {row['profile_id'] for row in view['user_panels']} == active
    assert view['privacy_redacted'] == (not active)
    assert view['primary_privacy_redacted'] == ('primary' not in active)
    assert bool(view['calendar']) == ('primary' in active)
    for row in view['user_panels']:
        assert row['calendar'][0]['summary'] == row['nickname']+' PRIVATE'
    if 'primary' not in active:
        assert view['agenda'] is None and view['todos'] == [] and view['notifications'] == []
        assert view['settings']['visible_calendar_ids'] == []
        voice = app.state.luma.voice_snapshot(authorized=True, now=now)
        assert voice['privacy_redacted'] and voice['voice_calendar']['events'] == []
        assert voice['voice_todos'] == []


def test_ancs_authorization_loss_redacts_before_legacy_grace_or_worker_cleanup(app_rig):
    app, users, link, now = app_rig
    for user in users: link(user.id)
    lost = users[2]
    app.state.bluetooth.runtime(lost.id).remote_authorized.clear()
    assert app.state.bluetooth.runtime(lost.id).service.state.phone_connected
    view = app.state.luma.snapshot(now)
    assert lost.id not in {row['profile_id'] for row in view['user_panels']}
    assert len(view['user_panels']) == 4
    app.state.bluetooth.runtime('primary').remote_authorized.clear()
    assert app.state.luma.state.phone_connected
    view = app.state.luma.snapshot(now)
    assert view['calendar'] == [] and view['privacy_redacted'] is False
    assert len(view['user_panels']) == 3


def test_guest_without_integration_is_roster_only_and_keeps_public_standby(app_rig):
    app, users, link, now = app_rig
    uid = users[1].id
    app.state.profiles.update_personal(uid, {'visible_calendar_ids': [], 'todo_calendar_id': None})
    link(uid)
    view = app.state.luma.snapshot(now)
    assert view['users'][0]['profile_id'] == uid
    assert view['privacy_redacted'] and view['user_panels'] == []
    assert view['calendar'] == []


def test_primary_sleep_and_notifications_do_not_leak_to_guest_panels(app_rig):
    app, users, link, now = app_rig
    service = app.state.luma
    service.update_settings({'sleep_calendar_ids': ['sleep']}, now)
    sleep = CalendarEvent('sleep', 'sleep', 'Sleep', now-timedelta(hours=1), now+timedelta(hours=1))
    service.replace_events(service.events+[sleep], now)
    link(users[1].id)
    view = service.snapshot(now)
    assert view['state']['display_power'] == 'off'
    assert view['privacy_redacted'] and view['user_panels'] == []
    service.receive_notification(PhoneNotification('n1', 'net.whatsapp.WhatsApp', 'WhatsApp', 'Primary private', 'Body', now))
    assert not service.claim_notification_chime(now)['play']


def test_each_personal_timer_alarm_uses_real_device_claim_and_keeps_room_timer(app_rig):
    app, users, link, now = app_rig
    service = app.state.luma
    bank = service.personal_timers
    clock = Mock(return_value=100.)
    bank.clock = clock
    bank.tick(now, trusted=True)
    for user in users:
        timer = bank.for_user(user.id)
        timer.execute('start_timer', {'seconds': 1, 'label': user.nickname+' private'}, now=now)
    clock.return_value = 102.
    bank.tick(now+timedelta(seconds=2), trusted=True)
    view = service.snapshot(now)
    assert len(view['personal_timers']) == 5
    assert all(row['label'] == 'Timer' for row in view['personal_timers'])
    assert service.timer.snapshot()['status'] == 'idle'
    assert service.claim_timer_chime()
    assert not service.claim_timer_chime()


def test_state_http_route_exposes_present_panels_but_no_absent_primary_data(app_rig):
    app, users, link, _ = app_rig
    link(users[1].id)
    response = TestClient(app).get('/api/v1/state')
    assert response.status_code == 200
    assert 'Primary PRIVATE' not in response.text
    assert users[1].nickname+' PRIVATE' in response.text


def test_primary_timer_alarm_route_claims_personal_completion(app_rig):
    app, users, _, now = app_rig
    clock = Mock(return_value=100.)
    app.state.luma.personal_timers.clock = clock
    timer = app.state.luma.personal_timers.for_user(users[1].id)
    timer.tick(now, trusted=True)
    timer.execute('start_timer', {'seconds': 1}, now=now)
    clock.return_value = 102.
    timer.tick(now+timedelta(seconds=2), trusted=True)
    client = TestClient(app)
    assert client.post('/api/v1/device/timer-chime').json()['play']
    assert not client.post('/api/v1/device/timer-chime').json()['play']
