import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from luma.companion_settings import validate_operations, READS, POSTS
from luma.game_handoff import GameHandoff
from test_companion_api import rig, dispatch, client, envelope
from test_companion_multiuser_api import app_rig, browser
from test_companion_profiles import enroll_user

PATH = '/remote/api/hub-settings'


def operation(path='settings', method='GET', body=None, confirmed=False):
    return {'method': method, 'path': '/api/v1/' + path, 'body': body or {}, 'confirmed': confirmed}


async def settings(rig, *ops):
    return await dispatch(rig, 'POST', PATH, {'operations': list(ops)})


@pytest.mark.asyncio
async def test_primary_batch_uses_full_shared_settings_and_validators(rig):
    result = await settings(rig, operation(), operation('security/status'), operation('users'))
    assert result.status_code == 200
    rows = result.json()['results']
    assert len(rows) == 3 and all(row['status'] == 200 for row in rows)
    assert 'audio_output' in rows[0]['body'] and 'phone_address' in rows[0]['body']
    changed = await settings(rig, operation('settings', 'PATCH', {'audio_output': 'hdmi'}))
    assert changed.status_code == 200 and rig[0].state.luma.settings.audio_output == 'hdmi'
    bad = await settings(rig, operation('settings', 'PATCH', {'audio_output': 'SECRET_BAD_ROUTE'}))
    assert bad.json()['results'][0]['status'] == 422 and 'SECRET_BAD_ROUTE' not in bad.text
    assert rig[0].state.luma.settings.audio_output == 'hdmi'


@pytest.mark.asyncio
async def test_locked_or_absent_primary_cannot_read_full_settings(rig):
    app, _, device = rig
    pending = envelope(rig, 'POST', PATH, {'operations': [operation()]})
    app.state.admin.lock_remote(device)
    async with client(app) as c:
        result = await c.post('/api/v1/companion/dispatch', json=pending)
    assert result.status_code == 403 and result.json()['code'] == 'admin_required'


@pytest.mark.asyncio
async def test_secondary_cannot_use_bridge_even_with_primary_pin(app_rig):
    result = await settings(browser(app_rig), operation('users'))
    assert result.status_code == 403 and 'phone_address' not in result.text


@pytest.mark.parametrize('op', [operation('../settings'), operation('device/report', 'POST'),
    operation('voice/calibration/sample', 'POST'), operation('google/authorize', 'POST'),
    operation('user-self/google/authorize', 'POST'), operation('settings?x=1'),
    {'method': 'GET', 'path': 'https://example.com', 'body': {}, 'confirmed': True},
    {**operation(), 'headers': {'Cookie': 'anything'}}, {**operation(), 'confirmed': 'yes'},
    operation('settings', body={'unexpected': True})])
def test_never_arbitrary_proxy_or_device_reports(op):
    with pytest.raises(HTTPException):
        validate_operations({'operations': [op]})


def test_only_gets_can_batch_and_mutations_need_confirmed_review():
    with pytest.raises(HTTPException):
        validate_operations({'operations': [operation()] * 13})
    with pytest.raises(HTTPException):
        validate_operations({'operations': [operation(), operation('settings', 'PATCH', {'theme': 'hearth'})]})
    with pytest.raises(HTTPException) as error:
        validate_operations({'operations': [operation('updates/install', 'POST', {'candidate_id': 'a'})]})
    assert error.value.status_code == 409
    assert validate_operations({'operations': [operation('tailscale', 'POST', {'action': 'status'})]})


@pytest.mark.asyncio
async def test_primary_secondary_wizard_cookie_stays_on_server(rig):
    app = rig[0]
    created = await settings(rig, operation('users/manage', 'POST', {'action': 'create', 'nickname': 'Alex'}, True))
    assert created.status_code == 200 and created.json()['results'][0]['status'] == 200
    assert 'luma_personal_setup' not in created.text
    status = await settings(rig, operation('user-self/status'))
    assert status.json()['results'][0]['status'] == 200
    assert status.json()['results'][0]['body']['nickname'] == 'Alex'
    assert len(app.state.profiles.list()) == 2


@pytest.mark.asyncio
async def test_personal_wizard_grant_isolated_between_primary_browsers(rig):
    app = rig[0]
    assert (await settings(rig, operation('users/manage', 'POST', {'action': 'create', 'nickname': 'Alex'}, True))).status_code == 200
    key, device = enroll_user(app.state.companion, 'primary')
    app.state.admin.unlock_remote('123456', device, app.state.companion._phone('primary'))
    other = await settings((app, key, device), operation('user-self/status'))
    assert other.json()['results'][0]['status'] == 403
    own = await settings(rig, operation('user-self/status'))
    assert own.json()['results'][0]['body']['nickname'] == 'Alex'


@pytest.mark.asyncio
async def test_sensitive_changes_require_fresh_pin_not_just_confirmation(rig):
    admin = rig[0].state.admin
    now = admin.clock();admin.clock = lambda: now + 61
    assert (await settings(rig, operation())).status_code == 200
    result = await settings(rig, operation('users/manage', 'POST', {'action': 'create', 'nickname': 'Alex'}, True))
    assert result.status_code == 403 and result.json()['fresh'] is True
    assert len(rig[0].state.profiles.list()) == 1


@pytest.mark.asyncio
async def test_disconnect_while_shared_settings_waits_prevents_commit(rig):
    app = rig[0];before = app.state.luma.settings.timezone
    payload = envelope(rig, 'POST', PATH, {'operations': [operation('settings', 'PATCH', {'timezone': 'UTC'})]})
    lock = app.state.google_sync_lock
    await lock.acquire()
    try:
        async with client(app) as c:
            task = asyncio.create_task(c.post('/api/v1/companion/dispatch', json=payload))
            await asyncio.sleep(.05)
            assert not task.done()
            app.state.bluetooth.remote_authorized.clear()
            lock.release()
            result = await task
        assert result.status_code == 403 and app.state.luma.settings.timezone == before
    finally:
        if lock.locked(): lock.release()


@pytest.mark.asyncio
async def test_backup_export_uses_wall_not_phone_checkpoints(rig):
    app = rig[0]
    app.state.game_handoff.capture = AsyncMock(return_value={})
    result = await settings(rig, operation('backups/export', 'POST', {
        'volume_id': 'a'*32, 'passphrase': 'test secret phrase', 'confirm_passphrase': 'test secret phrase',
        'games': {'phone': 'not a wall save'}}, True))
    assert result.status_code == 200  # Real USB not present; no hardware claims.
    app.state.game_handoff.capture.assert_awaited_once()
    assert 'test secret phrase' not in result.text and 'not a wall save' not in result.text


@pytest.mark.asyncio
async def test_handoff_clears_after_ack_and_rechecks_authority():
    handoff = GameHandoff();checks = []
    task = asyncio.create_task(handoff.capture(lambda: checks.append(True)))
    await asyncio.sleep(0)
    assert handoff.pending['action'] == 'capture'
    handoff.future.set_result({})
    assert await task == {} and len(checks) == 2
    assert handoff.pending is None and handoff.future is None


def test_all_reviewed_literal_routes_exist_in_app(rig):
    routes = {(method, route.path) for route in rig[0].routes for method in getattr(route, 'methods', [])}
    assert all(('GET', '/api/v1/'+path) in routes for path in READS)
    assert all(('POST', '/api/v1/'+path) in routes for path in POSTS)
