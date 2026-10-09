"""Clock-driven greeting tests; synthetic ANCS is not a radio/audio test."""
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from luma.api import create_app
from luma.models import CalendarEvent
from luma.presence_transitions import PresenceTransitions


@pytest.fixture
def transitions():
    clock = Mock(return_value=100.)
    flow = PresenceTransitions(clock=clock, startup_seconds=0)
    flow.observe({'p': 'Brian', 'g': 'Alex'}, set())
    return flow, clock, {'p': 'Brian', 'g': 'Alex'}


def test_three_second_arrival_then_exact_five_second_display(transitions):
    flow, clock, names = transitions
    flow.observe(names, {'p'})
    clock.return_value = 102.99
    flow.observe(names, {'p'})
    assert flow.view(names) is None
    clock.return_value = 103.
    assert flow.observe(names, {'p'})
    view = flow.view(names)
    assert view['arriving'] == ['Brian'] and view['leaving'] == []
    assert view['remaining_ms'] == 5000
    assert flow.claim_chime(audible=True)
    assert not flow.claim_chime(audible=True)
    clock.return_value = 108.
    assert flow.observe(names, {'p'})
    assert flow.view(names) is None
    assert not flow.claim_chime(audible=True)


def test_departure_grace_does_not_replay_brief_disconnect(transitions):
    flow, clock, names = transitions
    flow.observe(names, {'p'}, suppressed=True)
    flow.observe(names, set())
    clock.return_value = 114.99
    flow.observe(names, set())
    assert flow.view(names) is None
    flow.observe(names, {'p'})
    clock.return_value = 130.
    flow.observe(names, {'p'})
    assert flow.view(names) is None
    flow.observe(names, set())
    clock.return_value = 145.
    flow.observe(names, set())
    assert flow.view(names)['leaving'] == ['Brian']


def test_boot_settling_is_baseline_not_a_saved_greeting():
    clock = Mock(return_value=100.)
    flow = PresenceTransitions(clock=clock)
    names = {'p': 'Brian', 'g': 'Alex'}
    flow.observe(names, set())
    clock.return_value = 110.
    flow.observe(names, {'p'})
    clock.return_value = 125.
    flow.observe(names, {'p', 'g'})
    clock.return_value = 130.
    flow.observe(names, {'p', 'g'})
    assert flow.view(names) is None
    assert not flow.claim_chime(audible=True)


def test_simultaneous_mixed_changes_coalesce_and_queue_without_reset(transitions):
    flow, clock, names = transitions
    flow.observe(names, {'p'}, suppressed=True)
    flow.observe(names, set())
    clock.return_value = 112.
    flow.observe(names, {'g'})
    clock.return_value = 115.
    flow.observe(names, {'g'})
    view = flow.view(names)
    assert view['leaving'] == ['Brian'] and view['arriving'] == ['Alex']
    names['third'] = 'Sam'
    clock.return_value = 116.
    flow.observe(names, {'g', 'third'})
    clock.return_value = 119.
    flow.observe(names, {'g', 'third'})
    assert flow.view(names)['id'] == view['id']
    clock.return_value = 120.
    flow.observe(names, {'g', 'third'})
    assert flow.view(names)['arriving'] == ['Sam']
    assert flow.view(names)['remaining_ms'] == 5000


@pytest.mark.parametrize('target', [True, False])
def test_active_message_cancels_on_reverse_before_debounce(transitions, target):
    flow, clock, names = transitions
    flow.observe(names, set() if target else {'p'}, suppressed=True)
    present = {'p'} if target else set()
    flow.observe(names, present)
    clock.return_value += 3 if target else 15
    flow.observe(names, present)
    assert flow.view(names)
    flow.observe(names, set() if target else {'p'})
    assert flow.view(names) is None


def test_suppression_and_muting_consume_without_later_replay(transitions):
    flow, clock, names = transitions
    flow.observe(names, {'g'})
    clock.return_value = 103.
    flow.observe(names, {'g'})
    assert not flow.claim_chime(audible=False)
    assert not flow.claim_chime(audible=True)
    flow.observe(names, {'g'}, suppressed=True)
    clock.return_value = 200.
    flow.observe(names, {'g'})
    assert flow.view(names) is None
    flow.observe(names, set(), suppressed=True)
    flow.observe(names, set())
    assert flow.view(names) is None


def test_removal_and_rename_do_not_fake_a_presence_change(transitions):
    flow, clock, names = transitions
    flow.observe(names, {'p'}, suppressed=True)
    names['p'] = 'New nickname'
    flow.observe(names, {'p'})
    assert flow.view(names) is None
    del names['p']
    flow.observe(names, set())
    clock.return_value = 120.
    flow.observe(names, set())
    assert flow.view(names) is None


@pytest.fixture
def app_rig(tmp_path):
    app = create_app(data_dir=tmp_path)
    service = app.state.luma
    service.display_clock_trusted = lambda: True
    now = datetime.now(UTC)
    service.update_settings({'onboarding_completed': True}, now)
    profiles = app.state.profiles
    guest = profiles.create_secondary('Alex')
    profiles.bind_phone(guest.id, 'AA:BB:CC:DD:EE:02')
    profiles.set_setup(guest.id, 'ready', wall_share_approved=True)
    child = app.state.bluetooth.runtime(guest.id)
    # Explicit controllable synthetic ANCS lease, not phone_connected alone.
    child.remote_authorized.clock = lambda: 100.
    def link():
        child.remote_authorized.begin(guest.phone_address or 'AA:BB:CC:DD:EE:02', '/phone', '/source')
        child.remote_authorized.heartbeat('AA:BB:CC:DD:EE:02')
        child.service.phone_seen(now)
    clock = Mock(return_value=100.)
    service.presence_transitions = PresenceTransitions(clock=clock, startup_seconds=0)
    service.snapshot(now)
    return app, service, child, link, clock, now


def test_guest_only_arrival_and_last_departure_chime_without_primary_data(app_rig):
    _, service, child, link, clock, now = app_rig
    link()
    assert service.snapshot(now)['presence_transition'] is None
    clock.return_value = 103.
    view = service.snapshot(now)
    assert view['privacy_redacted']  # Guest intentionally has no calendars.
    assert view['presence_transition']['arriving'] == ['Alex']
    assert service.claim_notification_chime(now) == {'play': True, 'volume': 35}
    assert not service.claim_notification_chime(now)['play']
    child.remote_authorized.clear()
    view = service.snapshot(now)
    assert not view['users'] and not view['user_panels'] and not view['calendar']
    assert view['presence_transition'] is None  # Cancel active stale greeting.
    clock.return_value = 118.
    assert service.snapshot(now)['presence_transition']['leaving'] == ['Alex']
    assert service.claim_notification_chime(now)['play']


@pytest.mark.parametrize('suppression', ['sleep', 'off', 'update', 'pending_update', 'room_timer', 'personal_timer', 'privacy'])
def test_app_priority_suppresses_and_consumes_pending_greetings(app_rig, suppression):
    _, service, child, link, clock, now = app_rig
    link()
    service.snapshot(now)
    if suppression == 'sleep':
        service.update_settings({'sleep_calendar_ids': ['sleep']}, now)
        service.replace_events([CalendarEvent('s', 'sleep', 'Sleep', now-timedelta(hours=1), now+timedelta(hours=1))], now)
    elif suppression == 'off':
        service.display.off(now)
    elif suppression == 'update':
        service.presence_update_busy = True
    elif suppression == 'pending_update':
        service.presence_update_pending = 1
    elif suppression == 'privacy':
        service.state.forced_private = True
    else:
        timer = service.timer if suppression == 'room_timer' else service.personal_timers.for_user(child.profile_id)
        timer.data['status'] = 'complete'
    clock.return_value = 120.
    assert service.snapshot(now)['presence_transition'] is None
    assert not service.claim_notification_chime(now)['play']
    service.presence_update_busy = False
    service.presence_update_pending = 0
    service.state.forced_private = False
    service.timer.data['status'] = 'idle'
    for timer in service.personal_timers._timers.values():
        timer.data['status'] = 'idle'
    service.replace_events([], now)
    service.display.wake(now)
    clock.return_value = 180.
    assert service.snapshot(now+timedelta(minutes=1))['presence_transition'] is None
    assert not service.claim_notification_chime(now+timedelta(minutes=1))['play']


def test_untrusted_bond_is_not_an_arrival(app_rig):
    _, service, child, _, clock, now = app_rig
    child.service.phone_seen(now)
    service.snapshot(now)
    clock.return_value = 120.
    assert service.snapshot(now)['presence_transition'] is None


def test_http_read_at_deadline_cannot_consume_the_wall_publication(app_rig):
    _, service, _, link, clock, now = app_rig
    link()
    service.snapshot(now)
    queue = service.subscribe()
    clock.return_value = 103.
    view = service.snapshot(now)
    assert view['presence_transition']
    assert queue.get_nowait()['type'] == 'user.transition.updated'
    service.timer_tick(now)
    # A later tick may update display/timer, but does not repeat the greeting.
    while not queue.empty():
        assert queue.get_nowait()['type'] != 'user.transition.updated'
    service.unsubscribe(queue)


def test_partial_group_loss_retains_other_valid_arrival(transitions):
    flow, clock, names = transitions
    flow.observe(names, {'p', 'g'})
    clock.return_value = 103.
    flow.observe(names, {'p', 'g'})
    original = flow.view(names)
    flow.observe(names, {'g'})
    view = flow.view(names)
    assert view['id'] == original['id']
    assert view['arriving'] == ['Alex']
    assert view['remaining_ms'] == original['remaining_ms']


def test_existing_device_http_claim_consumes_guest_cue_without_names(app_rig):
    app, service, child, link, clock, _ = app_rig
    client = TestClient(app)
    link()
    assert client.post('/api/v1/device/notification-chime').json()['play'] is False
    clock.return_value = 103.
    assert client.get('/api/v1/state').json()['presence_transition']['arriving'] == ['Alex']
    assert client.post('/api/v1/device/notification-chime').json() == {'play': True, 'volume': 35}
    assert client.post('/api/v1/device/notification-chime').json()['play'] is False
    child.remote_authorized.clear()
    view = client.get('/api/v1/state').json()
    assert view['users'] == [] and view['presence_transition'] is None
    clock.return_value = 118.
    packet = client.post('/api/v1/device/notification-chime').json()
    assert packet == {'play': True, 'volume': 35}
    assert not service.primary_private_visible()
