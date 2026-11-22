"""Approved remote behavior when all registered Bluetooth phones are away."""
from dataclasses import replace
from datetime import timedelta
from unittest.mock import Mock

import pytest

from luma.profiles import PRIMARY_ID
from test_companion_api import client, dispatch, envelope
from test_companion_multiuser_api import browser
from test_multiuser_app import app_rig


def disconnect_everyone(app, users):
    for user in users:
        app.state.bluetooth.runtime(user.id).remote_authorized.clear()
    assert not app.state.luma.present_user_ids()


@pytest.mark.asyncio
@pytest.mark.parametrize('index', [0, 1])
async def test_away_preview_timer_calendar_choices_and_wall_privacy(app_rig, index):
    app, users, _, _ = app_rig
    rig = browser(app_rig, index)
    uid = users[index].id
    disconnect_everyone(app, users)
    # A remote must not require even a successful Bluetooth status read.
    app.state.companion.presence = Mock(side_effect=RuntimeError('radio unavailable'))
    result = await dispatch(rig, 'GET', '/remote/api/preview')
    assert result.status_code == 200
    view = result.json()
    assert view['profile_id'] == uid and view['privacy_redacted'] is False
    assert view['connected_users'] == [] and view['state']['phone_connected'] is False
    assert users[index].nickname+' PRIVATE' in result.text
    for other in users:
        if other.id != uid:
            assert other.nickname+' PRIVATE' not in result.text
    assert app.state.luma.snapshot()['privacy_redacted']
    assert app.state.profile_calendars.wall_panels() == []
    assert app.state.profile_calendars.projection(uid) is None
    changed = await dispatch(rig, 'PATCH', '/remote/api/personal-settings',
                             {'departure_prep_minutes': 9})
    assert changed.status_code == 200 and changed.json()['departure_prep_minutes'] == 9
    started = await dispatch(rig, 'POST', '/remote/api/command',
                             {'name': 'start_timer', 'value': {'seconds': 60, 'label': 'Tea'}})
    assert started.status_code == 200 and started.json()['preview']['timer']['label'] == 'Tea'
    assert app.state.luma.snapshot()['privacy_redacted']
    app.state.companion.presence.assert_not_called()


@pytest.mark.asyncio
async def test_primary_can_unlock_admin_and_change_settings_while_away(app_rig):
    app, users, _, _ = app_rig
    rig = browser(app_rig, 0)
    disconnect_everyone(app, users)
    denied = await dispatch(rig, 'PATCH', '/remote/api/settings', {'brightness': 42})
    assert denied.status_code == 403
    assert (await dispatch(rig, 'POST', '/remote/api/admin/unlock', {'pin': '000000'})).status_code == 403
    assert (await dispatch(rig, 'POST', '/remote/api/admin/unlock', {'pin': '123456'})).status_code == 200
    changed = await dispatch(rig, 'PATCH', '/remote/api/settings', {'brightness': 42})
    assert changed.status_code == 200 and app.state.luma.settings.brightness == 42
    assert (await dispatch(rig, 'POST', '/remote/api/admin/lock', {})).status_code == 200
    assert (await dispatch(rig, 'PATCH', '/remote/api/settings', {'brightness': 43})).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize('index', [0, 1])
async def test_task_completion_works_while_away_and_revocation_still_blocks(app_rig, index):
    app, users, _, _ = app_rig
    rig = browser(app_rig, index)
    uid = users[index].id
    disconnect_everyone(app, users)
    account = app.state.profile_calendars.account(uid)
    app.state.profiles.update_personal(uid, {'todo_calendar_id': 'tasks', 'todo_completed_color_id': '8'})
    day = account.events[0].start.replace(hour=0, minute=0, second=0, microsecond=0)
    task = replace(account.events[0], id='awaytask', calendar_id='tasks', start=day,
                   end=day+timedelta(days=1), all_day=True, calendar_writable=True, etag='"away-v1"')
    account.events = [task]
    account.google.recolor_task = Mock(return_value=replace(task, event_color_id='8', etag='"away-v2"'))
    result = await dispatch(rig, 'POST', '/remote/api/todos/complete', {
        'calendar_id': 'tasks', 'event_id': task.id, 'etag': task.etag, 'completed': True})
    assert result.status_code == 200 and result.json()['todos'][0]['completed']
    assert account.events[0].event_color_id == '8'
    assert app.state.profile_calendars.wall_panels() == []
    pending = envelope(rig, 'GET', '/remote/api/preview')
    app.state.companion.revoke('123456', rig[2])
    async with client(app) as caller:
        assert (await caller.post('/api/v1/companion/dispatch', json=pending)).status_code == 403


@pytest.mark.asyncio
async def test_secondary_still_cannot_use_primary_settings_when_away(app_rig):
    app, users, _, _ = app_rig
    rig = browser(app_rig, 1)
    disconnect_everyone(app, users)
    before = app.state.luma.settings.brightness
    for method, path, value in [
        ('POST', '/remote/api/admin/unlock', {'pin': '123456'}),
        ('PATCH', '/remote/api/settings', {'brightness': 42}),
        ('POST', '/remote/api/updates/check', {}),
    ]:
        assert (await dispatch(rig, method, path, value)).status_code == 403
    assert app.state.luma.settings.brightness == before
    assert app.state.profiles.get(PRIMARY_ID).id == PRIMARY_ID
