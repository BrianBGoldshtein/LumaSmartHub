"""Real local/signed controllers; no cloud, owner radio, or installer mutation."""
import asyncio

import pytest
from unittest.mock import AsyncMock, Mock

from luma.api import create_app
from luma.admin_authority import COOKIE, FRESH_SECONDS, LEASE_SECONDS
from test_companion_api import client, dispatch, rig
from test_companion_multiuser_api import browser
from test_multiuser_app import app_rig


@pytest.fixture
def protected(tmp_path):
    app = create_app(data_dir=tmp_path)
    app.state.security.set_pin('123456')
    clock = [0.0]
    app.state.admin.clock = lambda: clock[0]
    return app, clock


async def unlock(connection):
    response = await connection.post('/api/v1/admin/unlock', json={'pin':'123456'})
    assert response.status_code == 200
    return response


@pytest.mark.asyncio
async def test_cookie_unlock_lock_and_fixed_lifetime(protected):
    app, clock = protected
    async with client(app) as connection:
        assert (await connection.get('/api/v1/settings')).json()['code'] == 'admin_required'
        status = (await connection.get('/api/v1/admin/status')).json()
        assert status == {'configured':True,'unlocked':False,'expires_in_seconds':0,'bootstrap':False}
        response = await unlock(connection)
        cookie = response.headers['set-cookie']
        assert 'HttpOnly' in cookie and 'SameSite=strict' in cookie and 'Path=/api/v1' in cookie
        assert COOKIE not in response.text
        assert (await connection.get('/api/v1/settings')).status_code == 200
        assert (await connection.patch('/api/v1/settings',json={'brightness':38})).status_code == 200
        clock[0] = LEASE_SECONDS
        assert (await connection.patch('/api/v1/settings',json={'brightness':39})).status_code == 403
        assert app.state.luma.settings.brightness == 38
        await unlock(connection)
        assert (await connection.post('/api/v1/admin/lock')).status_code == 200
        assert (await connection.get('/api/v1/settings')).status_code == 403


@pytest.mark.asyncio
async def test_pin_creation_sets_cookie_and_cannot_replace_pin_without_fresh_owner(protected):
    app, clock = protected
    async with client(app) as connection:
        assert (await connection.post('/api/v1/security/pin',json={'pin':'789012'})).status_code == 403
        await unlock(connection)
        clock[0] = FRESH_SECONDS
        expired = await connection.post('/api/v1/security/pin',json={'pin':'789012'})
        assert expired.status_code == 403 and expired.json()['fresh'] is True
        assert app.state.security.verify_pin('123456')
        await unlock(connection)
        changed = await connection.post('/api/v1/security/pin',json={'pin':'789012'})
        assert changed.status_code == 200 and COOKIE in changed.headers['set-cookie']
        assert (await connection.get('/api/v1/settings')).status_code == 200
        assert app.state.security.verify_pin('789012')


@pytest.mark.asyncio
async def test_first_setup_can_provision_without_bypassing_updates(tmp_path,monkeypatch):
    app = create_app(data_dir=tmp_path)
    broker = AsyncMock()
    monkeypatch.setattr('luma.update_api.update_request',broker)
    async with client(app) as connection:
        assert (await connection.get('/api/v1/admin/status')).json()['bootstrap']
        assert (await connection.patch('/api/v1/settings',json={'theme':'hearth'})).status_code == 200
        assert (await connection.post('/api/v1/updates/install',json={'candidate_id':'a'*40})).status_code == 403
        broker.assert_not_awaited()
        response = await connection.post('/api/v1/security/pin',json={'pin':'123456'})
        assert response.status_code == 200 and 'HttpOnly' in response.headers['set-cookie']
        assert (await connection.get('/api/v1/admin/status')).json()['unlocked']


@pytest.mark.asyncio
async def test_actual_guest_presence_cannot_unlock_wall_settings(app_rig):
    app, users, link, _ = app_rig
    app.state.security.set_pin('123456')
    link(users[1].id)
    async with client(app) as connection:
        assert not (await connection.get('/api/v1/state')).json()['privacy_redacted']
        assert (await connection.patch('/api/v1/settings',json={'volume':20})).status_code == 403
        assert (await connection.get('/api/v1/google/calendars')).status_code == 403
        assert (await connection.post('/api/v1/commands',json={'name':'start_timer','value':{'seconds':60}})).status_code == 200
        assert (await connection.post('/api/v1/commands',json={'name':'set_volume','value':20})).status_code == 403
        assert (await connection.post('/api/v1/voice/phase',json={'phase':'listening'})).status_code == 200
        assert (await connection.post('/api/v1/device/timer-chime')).status_code == 200


@pytest.mark.asyncio
async def test_forged_headers_lan_token_and_cross_origin_are_not_primary_authority(protected):
    app, _ = protected
    async with client(app) as connection:
        forged = await connection.patch('/api/v1/settings',json={'brightness':20},
            headers={'x-luma-admin':'true','luma_admin_check':'approved'})
        assert forged.status_code == 403
        assert (await connection.post('/api/v1/admin/unlock',json={'pin':'123456'},
            headers={'origin':'https://evil.test'})).status_code == 403
    token = app.state.security.get_or_create_lan_token()
    async with client(app,'192.0.2.1') as connection:
        response = await connection.patch('/api/v1/settings',json={'brightness':20},headers={'x-luma-token':token})
        assert response.status_code == 403
        assert (await connection.post('/api/v1/admin/unlock',json={'pin':'123456'},headers={'x-luma-token':token})).status_code == 403


@pytest.mark.asyncio
async def test_expiry_while_waiting_for_lock_prevents_global_write(protected):
    app, clock = protected
    lock = app.state.google_sync_lock
    async with client(app) as connection:
        await unlock(connection)
        await lock.acquire()
        try:
            pending = asyncio.create_task(connection.patch('/api/v1/settings',json={'timezone':'UTC'}))
            await asyncio.sleep(.05)
            assert not pending.done()
            clock[0] = LEASE_SECONDS
            lock.release()
            result = await pending
            assert result.status_code == 403 and result.json()['code'] == 'admin_required'
            assert app.state.luma.settings.timezone != 'UTC'
        finally:
            if lock.locked(): lock.release()


@pytest.mark.asyncio
async def test_private_provider_result_not_returned_after_owner_lease_expiry(protected):
    app, clock = protected
    def provider():
        clock[0] = LEASE_SECONDS
        return [{'id':'PRIVATE_CALENDAR'}]
    app.state.google.list_calendars = provider
    async with client(app) as connection:
        await unlock(connection)
        response = await connection.get('/api/v1/google/calendars')
        assert response.status_code == 403 and 'PRIVATE_CALENDAR' not in response.text


@pytest.mark.asyncio
async def test_primary_remote_has_explicit_pin_unlock_but_personal_timer_needs_no_pin(rig):
    app, _, device = rig
    app.state.admin.lock_remote(device)
    status = await dispatch(rig,'GET','/remote/api/admin/status')
    assert status.status_code == 200 and not status.json()['unlocked']
    assert (await dispatch(rig,'GET','/remote/api/personal-settings')).status_code == 200
    assert (await dispatch(rig,'POST','/remote/api/command',{'name':'start_timer','value':{'seconds':60}})).status_code == 200
    denied = await dispatch(rig,'GET','/remote/api/settings')
    assert denied.status_code == 403 and denied.json()['code'] == 'admin_required'
    assert (await dispatch(rig,'PATCH','/remote/api/settings',{'brightness':20})).status_code == 403
    assert (await dispatch(rig,'POST','/remote/api/admin/unlock',{'pin':'123456'})).status_code == 200
    assert (await dispatch(rig,'PATCH','/remote/api/settings',{'brightness':20})).status_code == 200
    assert app.state.luma.settings.brightness == 20
    assert (await dispatch(rig,'POST','/remote/api/admin/lock',{})).status_code == 200
    assert (await dispatch(rig,'GET','/remote/api/settings')).status_code == 403


@pytest.mark.asyncio
async def test_guest_cannot_promote_with_known_primary_pin(app_rig):
    guest = browser(app_rig)
    response = await dispatch(guest,'POST','/remote/api/admin/unlock',{'pin':'123456'})
    assert response.status_code == 403
    assert not guest[0].state.admin.leases
    assert (await dispatch(guest,'POST','/remote/api/command',{'name':'start_timer','value':{'seconds':60}})).status_code == 200


@pytest.mark.asyncio
async def test_remote_policy_review_requires_pin_and_preserves_secondary_accounts(app_rig):
    guest = browser(app_rig)
    app = guest[0]
    previous = app.state.profiles.list()
    async with client(app) as connection:
        bad = await connection.post('/api/v1/companion/local',json={'action':'remote_policy_status','pin':'000000'})
        assert bad.status_code == 403
        status = await connection.post('/api/v1/companion/local',json={'action':'remote_policy_status','pin':'123456'})
        assert status.json()['policy'] == 'all_profiles'
        restricted = await connection.post('/api/v1/companion/local',json={'action':'remote_policy','pin':'123456','policy':'primary_only'})
        assert restricted.json()['policy'] == 'primary_only'
    assert app.state.profiles.list() == previous
    assert not app.state.companion._grants()


@pytest.mark.asyncio
async def test_remote_owner_expiry_at_settings_lock_is_fixed_admin_error(rig):
    app, _, device = rig
    clock = [0.0]
    app.state.admin.clock = lambda: clock[0]
    await dispatch(rig,'POST','/remote/api/admin/unlock',{'pin':'123456'})
    lock = app.state.google_sync_lock
    await lock.acquire()
    try:
        pending = asyncio.create_task(dispatch(rig,'PATCH','/remote/api/settings',{'timezone':'UTC'}))
        await asyncio.sleep(.05)
        assert not pending.done()
        clock[0] = LEASE_SECONDS
        lock.release()
        response = await pending
        assert response.status_code == 403 and response.json()['code'] == 'admin_required'
        assert app.state.luma.settings.timezone != 'UTC'
    finally:
        if lock.locked(): lock.release()
