"""Signed own-account setup progression, with no primary PIN promotion."""
import asyncio

import pytest

from test_companion_api import dispatch
from test_companion_multiuser_api import browser
from test_multiuser_app import app_rig


@pytest.mark.asyncio
@pytest.mark.parametrize('index', [0, 1])
async def test_remote_setup_is_resumable_and_sharing_is_own_only(app_rig, index):
    app, users, _, _ = app_rig
    rig = browser(app_rig, index)
    uid = users[index].id
    others = {user.id: app.state.profiles.get(user.id) for user in users if user.id != uid}
    for stage in ('remote', 'google', 'calendars', 'ready'):
        result = await dispatch(rig, 'POST', '/remote/api/setup',
            {'stage': stage, 'wall_share_approved': stage == 'ready'})
        assert result.status_code == 200
        assert result.json() == {'profile_id': uid, 'nickname': users[index].nickname,
            'setup_stage': stage, 'wall_share_approved': stage == 'ready'}
        saved = await dispatch(rig, 'GET', '/remote/api/setup')
        assert saved.json() == result.json()
        for other_id, before in others.items():
            assert app.state.profiles.get(other_id) == before
        assert 'phone_address' not in result.text and 'PRIVATE' not in result.text
        assert result.headers['cache-control'] == 'no-store'
    # Completion is not an administrative lease; secondary cannot update.
    if index:
        assert (await dispatch(rig, 'POST', '/remote/api/updates/check', {})).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [
    {}, {'stage': 'phone'}, {'stage': 'invented'}, {'stage': []},
    {'stage': 'ready', 'profile_id': 'primary'},
    {'stage': 'ready', 'wall_share_approved': 1},
    {'stage': 'ready', 'brightness': 90},
])
async def test_remote_setup_rejects_extra_authority_or_invalid_progress(app_rig, value):
    app, users, _, _ = app_rig
    rig = browser(app_rig)
    before = app.state.profiles.get(users[1].id)
    result = await dispatch(rig, 'POST', '/remote/api/setup', value)
    assert result.status_code == 422
    assert app.state.profiles.get(users[1].id) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('loss', ['disconnect', 'policy', 'remove'])
async def test_lost_authority_waiting_for_setup_lock_never_commits(app_rig, loss):
    app, users, _, _ = app_rig
    rig = browser(app_rig)
    uid = users[1].id
    account = app.state.profile_calendars.account(uid)
    before = app.state.profiles.get(uid)
    async with account.lock:
        pending = asyncio.create_task(dispatch(rig, 'POST', '/remote/api/setup',
            {'stage': 'ready', 'wall_share_approved': True}))
        await asyncio.sleep(.05)
        if loss == 'disconnect':
            app.state.bluetooth.runtime(uid).remote_authorized.clear()
        elif loss == 'policy':
            app.state.profiles.set_remote_policy('primary_only')
        else:
            app.state.profiles.remove(uid)
    result = await pending
    assert result.status_code == 403
    if loss != 'remove':
        assert app.state.profiles.get(uid) == before
