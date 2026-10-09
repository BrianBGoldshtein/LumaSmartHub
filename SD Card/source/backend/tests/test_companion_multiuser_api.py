"""Actual signed HTTP dispatch for own-account remotes with synthetic ANCS."""
import asyncio
import hashlib
import json
from datetime import timedelta
from itertools import product
from types import SimpleNamespace
from urllib.parse import urlencode, parse_qs, urlsplit
from unittest.mock import MagicMock, Mock

import pytest
from google.auth.exceptions import RefreshError

from luma.companion_google import AUTH_URI, TOKEN_URI, WEB_CLIENT_KEY
from luma.integrations.google_calendar import TOKEN_KEY, CALENDAR_SCOPE
from luma.models import CalendarEvent
from test_companion_api import client, dispatch, envelope, ORIGIN, IDENTITY
from test_companion_google import web_client
from test_companion_profiles import enroll_user
from test_multiuser_app import app_rig


def browser(app_rig, index=1):
    app, users, link, _ = app_rig
    app.state.security.set_pin('123456')
    link(users[index].id)
    key, device = enroll_user(app.state.companion, users[index].id)
    return app, key, device


@pytest.mark.asyncio
@pytest.mark.parametrize('index',[0,1])
async def test_cpu_sensor_available_to_authorized_own_remote_only(app_rig,index,tmp_path,monkeypatch):
    from luma import thermal
    sensor=tmp_path/'temp';sensor.write_bytes(b'56478\n')
    monkeypatch.setattr(thermal,'CPU_SENSOR',sensor)
    rig=browser(app_rig,index)
    response=await dispatch(rig,'GET','/remote/api/preview')
    assert response.status_code==200 and response.json()['device_temperature']['celsius']==56.5
    assert response.json()['profile_id']==app_rig[1][index].id
    sensor.unlink()
    response=await dispatch(rig,'GET','/remote/api/preview')
    assert response.json()['device_temperature']['status']=='unavailable'
    pending=envelope(rig,'GET','/remote/api/preview')
    app_rig[0].state.bluetooth.runtime(app_rig[1][index].id).remote_authorized.clear()
    async with client(rig[0]) as caller:
        response=await caller.post('/api/v1/companion/dispatch',json=pending)
    assert response.status_code==403 and 'device_temperature' not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize('index', [0, 1])
@pytest.mark.parametrize('others', list(product([False, True], repeat=4)))
async def test_preview_is_own_only_for_every_other_phone_presence_combination(app_rig, index, others):
    app, users, link, _ = app_rig
    rig = browser(app_rig, index)
    for user, present in zip([user for position, user in enumerate(users) if position != index], others):
        if present: link(user.id)
    result = await dispatch(rig, 'GET', '/remote/api/preview')
    assert result.status_code == 200
    assert result.json()['profile_id'] == users[index].id
    assert result.json()['role'] == ('primary' if index == 0 else 'secondary')
    assert users[index].nickname+' PRIVATE' in result.text
    for user in [user for position, user in enumerate(users) if position != index]:
        assert user.nickname+' PRIVATE' not in result.text
    assert 'phone_address' not in result.text and 'notifications' not in result.text
    assert result.headers['cache-control'] == 'no-store'


@pytest.mark.asyncio
@pytest.mark.parametrize('method,path,value', [
    ('GET', '/remote/api/device/fan', None),
    ('POST', '/remote/api/device/fan', {'action':'always_on', 'pin':'123456'}),
    ('GET', '/remote/api/updates/status', None),
    ('POST', '/remote/api/updates/check', {}),
    ('POST', '/remote/api/updates/install', {'pin':'123456'}),
    ('POST', '/remote/api/google/web-client', web_client()),
    ('PATCH', '/remote/api/settings', {'brightness': 20}),
    ('PATCH', '/remote/api/settings', {'theme': 'hearth'}),
    ('PATCH', '/remote/api/settings', {'sleep_calendar_ids': ['sleep']}),
    ('PATCH', '/remote/api/settings', {'profile_id': 'primary'}),
    ('POST', '/remote/api/command', {'name': 'screen_off'}),
    ('POST', '/remote/api/command', {'name': 'set_volume', 'value': 20}),
    ('POST', '/remote/api/command', {'name': 'start_timer', 'value': 5, 'profile_id': 'primary'}),
])
async def test_guest_cannot_reach_primary_controls_even_with_primary_pin_in_body(app_rig, method, path, value):
    rig = browser(app_rig)
    app = rig[0]
    before = app.state.luma.settings
    response = await dispatch(rig, method, path, value)
    assert response.status_code == 403
    assert app.state.luma.settings == before
    assert app.state.companion.storage.get_secret(WEB_CLIENT_KEY) is None


@pytest.mark.asyncio
async def test_guest_can_change_only_own_calendar_and_reminder_preferences(app_rig):
    app, users, _, _ = app_rig
    rig = browser(app_rig)
    previous = app.state.profiles.get('primary').personal
    result = await dispatch(rig, 'PATCH', '/remote/api/settings',
                            {'visible_calendar_ids': ['guest-calendar'], 'departure_prep_minutes': 7})
    assert result.status_code == 200
    assert result.json()['visible_calendar_ids'] == ['guest-calendar']
    assert app.state.profiles.get('primary').personal == previous
    assert app.state.profiles.get(users[2].id).personal['visible_calendar_ids'] == ['events']
    assert result.headers['cache-control'] == 'no-store'


@pytest.mark.asyncio
async def test_personal_timers_for_primary_and_secondary_do_not_replace_room_or_each_other(app_rig):
    app, users, _, _ = app_rig
    guest = browser(app_rig)
    primary = browser(app_rig, 0)
    service = app.state.luma
    service.timer.execute('start_timer', {'seconds': 60, 'label': 'ROOM_PRIVATE'})
    for rig, label in [(guest, 'GUEST_PRIVATE'), (primary, 'PRIMARY_PRIVATE')]:
        response = await dispatch(rig, 'POST', '/remote/api/command',
                                  {'name': 'start_timer', 'value': {'seconds': 90, 'label': label}})
        assert response.status_code == 200 and response.json()['preview']['timer']['label'] == label
        assert 'ROOM_PRIVATE' not in response.text
    for rig, label in [(guest, 'GUEST_PRIVATE'), (primary, 'PRIMARY_PRIVATE')]:
        response = await dispatch(rig, 'GET', '/remote/api/preview')
        assert response.json()['timer']['label'] == label
        assert 'ROOM_PRIVATE' not in response.text
    await dispatch(guest, 'POST', '/remote/api/command', {'name': 'pause_timer'})
    assert service.personal_timers.for_user(users[1].id).snapshot()['status'] == 'paused'
    assert service.personal_timers.for_user('primary').snapshot()['status'] == 'running'
    assert service.timer.snapshot()['status'] == 'running'


@pytest.mark.asyncio
async def test_guest_provider_reads_own_client_and_disconnect_discards_private_response(app_rig):
    app, users, _, _ = app_rig
    rig = browser(app_rig)
    account = app.state.profile_calendars.account(users[1].id)
    primary = app.state.google.list_calendars = Mock(return_value=[{'id': 'PRIMARY_PRIVATE'}])
    account.google.list_calendars = Mock(return_value=[{'id': 'GUEST_PRIVATE'}])
    result = await dispatch(rig, 'GET', '/remote/api/google/calendars')
    assert result.status_code == 200 and result.json() == [{'id': 'GUEST_PRIVATE'}]
    primary.assert_not_called()
    def disconnect():
        app.state.bluetooth.runtime(users[1].id).remote_authorized.clear()
        return [{'id': 'DISCONNECTED_PRIVATE'}]
    account.google.list_calendars = disconnect
    result = await dispatch(rig, 'GET', '/remote/api/google/calendars')
    assert result.status_code == 403 and 'DISCONNECTED_PRIVATE' not in result.text


@pytest.mark.asyncio
async def test_guest_provider_failures_preserve_saved_events_and_do_not_expose_sdk_text(app_rig):
    app, users, _, _ = app_rig
    rig = browser(app_rig)
    account = app.state.profile_calendars.account(users[1].id)
    saved = list(account.events)
    account.google.fetch_events = Mock(side_effect=RefreshError('PRIVATE_PROVIDER_DATA', {'error': 'invalid_grant'}))
    response = await dispatch(rig, 'POST', '/remote/api/google/sync', {})
    assert response.status_code == 503 and 'PRIVATE_PROVIDER_DATA' not in response.text
    assert account.events == saved and account.status['reconnect_required']
    assert not app.state.profile_calendars.account('primary').status['reconnect_required']


@pytest.mark.asyncio
async def test_guest_provider_response_is_bounded_before_export(app_rig):
    app, users, _, _ = app_rig
    rig = browser(app_rig)
    app.state.profile_calendars.account(users[1].id).google.list_calendars = Mock(return_value=[{'id': 'PRIVATE_TOO_LARGE', 'summary': 'x'*(1024*1024)}])
    response = await dispatch(rig, 'GET', '/remote/api/google/calendars')
    assert response.status_code == 503 and 'PRIVATE_TOO_LARGE' not in response.text


@pytest.mark.asyncio
async def test_guest_settings_waiting_for_lock_fail_closed_on_policy_change(app_rig):
    app, users, _, _ = app_rig
    rig = browser(app_rig)
    lock = app.state.profile_calendars.account(users[1].id).lock
    payload = envelope(rig, 'PATCH', '/remote/api/settings', {'visible_calendar_ids': ['changed']})
    await lock.acquire()
    try:
        async with client(app) as connection:
            pending = asyncio.create_task(connection.post('/api/v1/companion/dispatch', json=payload))
            await asyncio.sleep(.05)
            assert not pending.done()
            app.state.profiles.set_remote_policy('primary_only')
            lock.release()
            response = await pending
        assert response.status_code == 403
        assert app.state.profiles.get(users[1].id).personal['visible_calendar_ids'] == ['events']
    finally:
        if lock.locked(): lock.release()


@pytest.mark.asyncio
async def test_local_policy_pin_clears_proofs_enrollment_and_all_pending_google_attempts(app_rig):
    app, users, _, _ = app_rig
    rig = browser(app_rig)
    auth = app.state.companion
    auth.challenge(rig[2], ORIGIN, IDENTITY, 'GET', '/remote/api/preview', hashlib.sha256(b'').hexdigest())
    auth.issue_ticket('123456', ORIGIN, profile_id=users[1].id)
    app.state.companion_google.pending['synthetic'] = {'synthetic': True}
    async with client(app) as connection:
        denied = await connection.post('/api/v1/companion/local', json={'action':'remote_policy', 'pin':'111111', 'policy':'primary_only'})
        assert denied.status_code == 403 and auth.challenges
        result = await connection.post('/api/v1/companion/local', json={'action':'remote_policy', 'pin':'123456', 'policy':'primary_only'})
    assert result.status_code == 200 and result.json()['policy'] == 'primary_only'
    assert auth.ticket is auth.pending is None and auth.challenges == {}
    assert app.state.companion_google.pending == {}
    assert app.state.bluetooth.companion_presence(users[1].id).authorized
    assert app.state.profiles.get(users[1].id).wall_share_approved


@pytest.mark.asyncio
async def test_guest_google_consent_uses_shared_registration_but_commits_only_own_token(app_rig):
    app, users, _, _ = app_rig
    rig = browser(app_rig)
    app.state.companion.storage.set_secret(TOKEN_KEY, 'PRIMARY_OLD_TOKEN')
    app.state.companion.storage.set_secret(WEB_CLIENT_KEY, json.dumps(web_client()))
    status = await dispatch(rig, 'GET', '/remote/api/google/status')
    assert status.status_code == 200 and status.json()['web_configured']
    remote = app.state.companion_google_accounts[users[1].id]
    flow = MagicMock()
    factory = MagicMock(return_value=flow)
    flow.authorization_url.side_effect = lambda **_: (AUTH_URI+'?'+urlencode({'state': factory.call_args.kwargs['state']}), 'unused')
    flow.credentials = SimpleNamespace(refresh_token='GUEST_REFRESH', scopes=[CALENDAR_SCOPE], granted_scopes=None,
        to_json=lambda: json.dumps({'token':'GUEST_TOKEN', 'refresh_token':'GUEST_REFRESH', 'token_uri':TOKEN_URI}))
    remote.flow_factory = factory
    consent = await dispatch(rig, 'POST', '/remote/api/google/authorize', {'task_updates': False})
    assert consent.status_code == 200
    state = parse_qs(urlsplit(consent.json()['url']).query)['state'][0]
    async with client(app) as connection:
        result = await connection.post('/api/v1/companion/google-callback', json={
            'origin': ORIGIN, 'identity': IDENTITY, 'query': urlencode({'state':state, 'code':'fake-code'})})
    assert result.json() == {'connected': True}
    assert app.state.companion.storage.get_secret(TOKEN_KEY) == 'PRIMARY_OLD_TOKEN'
    assert json.loads(remote.storage.get_secret(TOKEN_KEY))['refresh_token'] == 'GUEST_REFRESH'
    assert remote.storage.get_secret(WEB_CLIENT_KEY) is None
    assert 'GUEST_REFRESH' not in result.text


@pytest.mark.asyncio
async def test_guest_completion_with_same_calendar_event_id_updates_only_own_account(app_rig):
    app, users, _, now = app_rig
    rig = browser(app_rig)
    for user in users:
        app.state.profiles.update_personal(user.id, {'todo_completed_color_id': '5'})
        account = app.state.profile_calendars.account(user.id)
        task = CalendarEvent('same_task', 'tasks', user.nickname+' TASK', now.replace(hour=0),
                             now.replace(hour=0)+timedelta(days=2), all_day=True, etag='revision', calendar_writable=True)
        account.events.append(task)
        account.google.task_write_authorized = Mock(return_value=True)
        account.google.recolor_task = Mock(return_value=CalendarEvent(**{
            **{field: getattr(task, field) for field in task.__dataclass_fields__}, 'event_color_id':'5', 'etag':'updated'}))
    response = await dispatch(rig, 'POST', '/remote/api/todos/complete',
        {'calendar_id':'tasks', 'event_id':'same_task', 'etag':'revision', 'completed':True})
    assert response.status_code == 200 and response.json()['todos'][0]['completed']
    for user in users:
        account = app.state.profile_calendars.account(user.id)
        assert account.google.recolor_task.call_count == (1 if user.id == users[1].id else 0)
        assert account.events[-1].event_color_id == ('5' if user.id == users[1].id else None)
