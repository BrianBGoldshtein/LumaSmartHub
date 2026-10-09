"""Local account read/chooser tests; no actual ASR, phone or speaker involved."""
from datetime import UTC, datetime, timedelta
from itertools import product
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from luma.api import create_app
from luma.models import CalendarEvent
from luma.voice_accounts import VoiceAccounts, split_account_phrase
from luma.voice_agent import select_command


@pytest.fixture
def rig(tmp_path):
    app = create_app(data_dir=tmp_path)
    service, profiles = app.state.luma, app.state.profiles
    service.display_clock_trusted = lambda: True
    now = datetime.now(UTC)
    service.update_settings({'onboarding_completed': True, 'voice_enabled': True, 'timezone': 'UTC'}, now)
    profiles.rename('primary', 'Brian')
    users = [profiles.get('primary')] + [profiles.create_secondary(name) for name in ['Alex', 'Sam', 'Casey', 'Robin']]
    for index, user in enumerate(users):
        profiles.bind_phone(user.id, f'AA:BB:CC:DD:EE:{index+1:02X}')
        profiles.set_setup(user.id, 'ready', wall_share_approved=True)
        profiles.update_personal(user.id, {'visible_calendar_ids': ['events'], 'todo_calendar_id': 'tasks'})
        account = app.state.profile_calendars.account(user.id)
        account.google.authorized = Mock(return_value=True)
        account.google.fetch_events = Mock(side_effect=AssertionError('Voice must not fetch Google'))
        account.events = [CalendarEvent('same-id', 'events', user.nickname+' PRIVATE EVENT', now+timedelta(minutes=30), now+timedelta(hours=1)),
                          CalendarEvent('same-task', 'tasks', user.nickname+' PRIVATE TASK', now-timedelta(days=1), now+timedelta(days=2), all_day=True)]
        account.status['last_synced'] = now.isoformat()
    service.machine.settings = profiles.storage.load_settings()
    service.replace_events(app.state.profile_calendars.account('primary').events, now)
    service.calendar_synced_at = now
    clock = Mock(return_value=100.)
    service.voice_accounts = VoiceAccounts(service, clock=clock)
    def link(uid):
        user = profiles.get(uid)
        child = app.state.bluetooth.runtime(uid)
        child.remote_authorized.clock = lambda: 100.
        child.remote_authorized.begin(user.phone_address, '/phone-'+uid, '/source-'+uid)
        child.remote_authorized.heartbeat(user.phone_address)
        child.service.phone_seen(now)
        return child
    return app, service, users, link, clock


@pytest.mark.parametrize('combination', list(product([False, True], repeat=5)))
def test_all_32_presence_combinations_choose_only_present_shared_accounts(rig, combination):
    app, service, users, link, _ = rig
    active = [user for user, present in zip(users, combination) if present]
    for user in active: link(user.id)
    response = TestClient(app).post('/api/v1/voice/command', json={'text': 'when is my next event'}).json()
    if not active:
        assert not response['accepted'] and 'private' in response['message']
    elif len(active) == 1:
        assert response['accepted'] and active[0].nickname+' PRIVATE EVENT' in response['message']
    else:
        assert not response['accepted'] and 'Whose' in response['message']
        view = service.snapshot()['voice_account_choice']
        assert {row['profile_id'] for row in view['users']} == {user.id for user in active}
    for user in users:
        if user not in active or len(active) != 1:
            assert user.nickname+' PRIVATE' not in response['message']


@pytest.mark.parametrize('phrase', ["what is on Alex's calendar today", 'Alex, what is on my calendar today',
    'what is on my calendar today for Alex', 'hey luma alex when is my next event'])
def test_explicit_name_does_not_get_lost_in_anonymous_primary_projection(rig, phrase):
    app, _, users, link, _ = rig
    link('primary');link(users[1].id)
    response = TestClient(app).post('/api/v1/voice/command', json={'text': phrase}).json()
    assert response['accepted'] and 'Alex PRIVATE EVENT' in response['message']
    assert 'Brian PRIVATE' not in response['message']


@pytest.mark.parametrize('phrase', ["what is on Brian's calendar today", "what is on Zoe's calendar today",
    "Brian, what is on Alex's calendar today", "what is on Brian's and Alex's calendars today", 'when is my next event for Zoe'])
def test_absent_unknown_or_multiple_explicit_names_never_fall_back(rig, phrase):
    app, _, users, link, _ = rig
    link(users[1].id)
    response = TestClient(app).post('/api/v1/voice/command', json={'text': phrase}).json()
    assert not response['accepted']
    assert 'PRIVATE EVENT' not in response['message']


def test_bond_and_wall_consent_are_not_voice_authority(rig):
    app, service, users, link, _ = rig
    child = link(users[1].id)
    app.state.profiles.set_setup(users[1].id, 'ready', wall_share_approved=False)
    response = service.voice_accounts.handle('Alex what is on my calendar today')
    assert not response['accepted']
    app.state.profiles.set_setup(users[1].id, 'ready', wall_share_approved=True)
    child.remote_authorized.clear()
    assert child.service.state.phone_connected
    assert not service.voice_accounts.handle('Alex what is on my calendar today')['accepted']


def test_spoken_selection_is_one_use_and_stored_request_has_no_transcript(rig):
    app, service, users, link, _ = rig
    link('primary');link(users[1].id)
    client = TestClient(app)
    assert not client.post('/api/v1/voice/command', json={'text': 'when is my next event'}).json()['accepted']
    assert set(service.voice_accounts.pending) == {'id', 'until', 'intent', 'eligible'}
    response = client.post('/api/v1/voice/command', json={'text': 'hey luma alex'}).json()
    assert response['accepted'] and 'Alex PRIVATE EVENT' in response['message']
    assert service.snapshot()['voice_account_choice'] is None
    again = client.post('/api/v1/voice/command', json={'text': 'Alex'}).json()
    assert not again['accepted'] and 'PRIVATE' not in again['message']


@pytest.mark.parametrize('change', ['disconnect', 'new_session', 'consent', 'remove', 'expiry', 'voice_off', 'update'])
def test_touch_choice_rechecks_original_generation_and_policy(rig, change):
    app, service, users, link, clock = rig
    link('primary');child = link(users[1].id)
    client = TestClient(app)
    client.post('/api/v1/voice/command', json={'text': 'when is my next event'})
    choice = service.snapshot()['voice_account_choice']['id']
    if change == 'disconnect': child.remote_authorized.clear()
    elif change == 'new_session': link(users[1].id)
    elif change == 'consent': app.state.profiles.set_setup(users[1].id, 'ready', wall_share_approved=False)
    elif change == 'remove': app.state.profiles.remove(users[1].id)
    elif change == 'expiry': clock.return_value = 130.
    elif change == 'voice_off': service.update_settings({'voice_enabled': False})
    else: service.presence_update_busy = True
    response = client.post('/api/v1/voice/account/choose', json={'choice_id': choice, 'profile_id': users[1].id}).json()
    assert not response['accepted'] and 'PRIVATE' not in response['message']
    assert service.voice_accounts.reply_job is None


def test_touch_reply_generated_on_claim_and_consumed_once(rig):
    app, service, users, link, _ = rig
    link('primary');link(users[1].id)
    client = TestClient(app)
    client.post('/api/v1/voice/command', json={'text': 'when is my next event'})
    choice = service.snapshot()['voice_account_choice']['id']
    selected = client.post('/api/v1/voice/account/choose', json={'choice_id': choice, 'profile_id': users[1].id}).json()
    assert selected == {'accepted': True, 'message': 'Answer queued', 'speak': False}
    assert set(service.voice_accounts.reply_job) == {'uid', 'generation', 'intent', 'until'}
    response = client.post('/api/v1/voice/account/reply').json()
    assert response['play'] and 'Alex PRIVATE EVENT' in response['message']
    assert 'Brian PRIVATE' not in response['message']
    assert client.post('/api/v1/voice/account/reply').json() == {'play': False}


@pytest.mark.parametrize('change', ['disconnect', 'new_session', 'consent', 'expiry'])
def test_queued_touch_reply_cannot_survive_lost_authority(rig, change):
    app, service, users, link, clock = rig
    link('primary');child = link(users[1].id)
    client = TestClient(app)
    client.post('/api/v1/voice/command', json={'text': 'when is my next event'})
    choice = service.snapshot()['voice_account_choice']['id']
    client.post('/api/v1/voice/account/choose', json={'choice_id': choice, 'profile_id': users[1].id})
    if change == 'disconnect': child.remote_authorized.clear()
    elif change == 'new_session': link(users[1].id)
    elif change == 'consent': app.state.profiles.set_setup(users[1].id, 'ready', wall_share_approved=False)
    else: clock.return_value = 110.
    assert client.post('/api/v1/voice/account/reply').json() == {'play': False}


def test_cancel_wrong_nonce_and_new_public_question_do_not_leave_private_backlog(rig):
    app, service, users, link, _ = rig
    link('primary');link(users[1].id)
    client = TestClient(app)
    client.post('/api/v1/voice/command', json={'text': 'when is my next event'})
    choice = service.snapshot()['voice_account_choice']['id']
    assert not client.post('/api/v1/voice/account/cancel', json={'choice_id': 'x'*43}).json()['accepted']
    assert service.voice_accounts.pending
    assert client.post('/api/v1/voice/account/cancel', json={'choice_id': choice}).json()['accepted']
    assert not service.voice_accounts.pending
    client.post('/api/v1/voice/command', json={'text': 'when is my next event'})
    assert client.post('/api/v1/voice/command', json={'text': 'what time is it'}).json()['accepted']
    assert service.voice_accounts.pending is None
    assert client.post('/api/v1/voice/account/reply').json() == {'play': False}


def test_secondary_good_morning_never_uses_primary_briefing(rig):
    app, _, users, link, _ = rig
    link(users[1].id)
    response = TestClient(app).post('/api/v1/voice/command', json={'text': 'good morning'}).json()
    assert response['accepted'] and 'Alex PRIVATE EVENT' in response['message']
    assert 'Brian PRIVATE' not in response['message']


def test_task_query_uses_selected_account_even_with_same_provider_ids(rig):
    app, _, users, link, _ = rig
    link('primary');link(users[1].id)
    response = TestClient(app).post('/api/v1/voice/command', json={'text': 'Alex what are my tasks today'}).json()
    assert response['accepted'] and 'Alex PRIVATE TASK' in response['message']
    assert 'Brian PRIVATE' not in response['message']


def test_primary_pin_override_stays_explicit_and_cannot_authorize_guest(rig):
    _, service, _, _, _ = rig
    service.unlock_with_pin()
    response = service.voice_accounts.handle('when is my next event')
    assert response['accepted'] and 'Brian PRIVATE EVENT' in response['message']
    response = service.voice_accounts.handle('Alex when is my next event')
    assert not response['accepted'] and 'PRIVATE EVENT' not in response['message']


def test_names_do_not_authorize_global_settings_or_other_account_ids(rig):
    app, service, users, link, _ = rig
    link(users[1].id)
    before = service.settings.theme
    assert not service.voice_accounts.handle('Alex change theme to arcade')['accepted']
    assert service.settings.theme == before
    external = TestClient(app, base_url='http://luma.local')
    assert external.get('/api/v1/voice/accounts/context').status_code == 403
    assert external.post('/api/v1/voice/account/choose', json={'choice_id': 'x'*43, 'profile_id': 'primary'}).status_code == 403


@pytest.mark.parametrize('phrase', ['Alex when is my next event', "when is Alex's next event", 'when is my next event for Alex'])
def test_decoder_preserves_explicit_name_without_weakening_read_intent_agreement(phrase):
    names = {'primary': 'Brian', 'guest': 'Alex'}
    selected, reason = select_command('when is my next event', 'hey luma '+phrase, 'hey luma', account_names=names)
    assert selected.casefold() == phrase.casefold() and reason == 'account_read'
    assert select_command('what is on my calendar tomorrow', 'hey luma '+phrase, 'hey luma', account_names=names)[0] is None
    assert select_command('change theme to arcade', 'hey luma Alex change theme to arcade', 'hey luma', account_names=names)[0] is None
    assert select_command('', 'hey luma Alex', 'hey luma', account_names=names) == ('alex', 'account_name')


def test_names_with_spaces_unicode_or_apostrophes_use_whole_bounded_syntax():
    names = {'a': 'Mary Jane', 'b': "O'Neil", 'c': 'José'}
    assert split_account_phrase("what is on Mary Jane's calendar today", names)[1:] == ('a', True)
    assert split_account_phrase("what is on O’Neil’s calendar today", names)[1:] == ('b', True)
    assert split_account_phrase('José, when is my next event', names)[1:] == ('c', True)
    assert split_account_phrase('start a timer titled Mary Jane', names)[1:] == (None, False)
    assert split_account_phrase('start a timer for ten minutes', names)[1:] == (None, False)
    assert split_account_phrase("start a timer for ten minutes titled Mary's calendar", names)[1:] == (None, False)


def test_personal_read_selection_does_not_capture_shared_custom_timer_slots(rig):
    app, service, _, _, _ = rig
    response = TestClient(app).post('/api/v1/voice/command', json={
        'text': "start a timer for ten seconds titled Mary's calendar"}).json()
    assert response['accepted']
    assert service.timer.snapshot()['label'] == "mary's calendar"
    assert service.voice_accounts.pending is None


def test_named_public_time_does_not_require_a_phone_or_choose_primary_data(rig):
    app, service, _, _, _ = rig
    response = TestClient(app).post('/api/v1/voice/command', json={'text': 'Alex what time is it'}).json()
    assert response['accepted'] and response['message'].startswith('It is ')
    assert service.voice_accounts.pending is None and 'PRIVATE' not in response['message']


def test_repeated_morning_does_not_create_a_second_account_briefing(rig):
    app, service, users, link, _ = rig
    link('primary');link(users[1].id)
    client = TestClient(app)
    first = client.post('/api/v1/voice/command', json={'text': 'good morning'}).json()
    assert 'Whose' in first['message']
    choice = service.snapshot()['voice_account_choice']['id']
    answer = client.post('/api/v1/voice/account/choose', json={
        'choice_id': choice, 'profile_id': users[1].id}).json()
    assert answer['accepted']
    assert client.post('/api/v1/voice/account/reply').json()['play']
    repeated = client.post('/api/v1/voice/command', json={'text': 'Alex good morning'}).json()
    assert 'PRIVATE' not in repeated['message'] and 'Whose' not in repeated['message']
    assert service.voice_accounts.pending is None and service.voice_accounts.reply_job is None
