"""Real fixed wall APIs with synthetic ANCS/provider; no owner devices."""
import asyncio
from dataclasses import replace
from datetime import timedelta
from itertools import product
from unittest.mock import Mock

import pytest

from luma.models import CalendarEvent, Command, CommandName
from luma.api import create_app
from luma.user_setup import COOKIE, wall_cookie
from test_companion_api import client
from test_multiuser_app import app_rig

PREFIX = '/api/v1/user-self/wall/'


async def approve_all(app, connection, users):
    app.state.security.set_pin('123456')
    assert (await connection.post('/api/v1/admin/unlock', json={'pin':'123456'})).status_code == 200
    for user in users:
        result = await connection.post('/api/v1/users/manage', json={'action':'resume','profile_id':user.id})
        assert result.status_code == 200
        assert wall_cookie(user.id) in connection.cookies
        assert 'HttpOnly' in result.headers['set-cookie'] and 'SameSite=strict' in result.headers['set-cookie']
    await connection.post('/api/v1/admin/lock')


@pytest.mark.asyncio
@pytest.mark.parametrize('combination', list(product([False,True], repeat=5)))
async def test_every_presence_combination_retains_only_live_independent_wall_grants(app_rig, combination):
    app, users, link, _ = app_rig
    app.state.luma.update_settings({'onboarding_completed':True})
    for user, present in zip(users, combination):
        if present: link(user.id)
    async with client(app) as connection:
        await approve_all(app, connection, users)
        visible = await connection.get(PREFIX+'access')
        assert {row['profile_id'] for row in visible.json()['users']} == {user.id for user,present in zip(users,combination) if present}
        assert visible.headers['cache-control'] == 'no-store'
        for user, present in zip(users, combination):
            result = await connection.get(PREFIX+'preview', params={'profile_id':user.id})
            assert result.status_code == (200 if present else 403)
            assert 'PRIVATE' not in result.text and 'calendar' not in result.json()


@pytest.mark.asyncio
async def test_cookie_selector_cannot_impersonate_other_account_or_administration(app_rig):
    app, users, link, _ = app_rig
    app.state.luma.update_settings({'onboarding_completed':True})
    for user in users: link(user.id)
    async with client(app) as connection:
        app.state.security.set_pin('123456')
        await connection.post('/api/v1/admin/unlock', json={'pin':'123456'})
        await connection.post('/api/v1/users/manage', json={'action':'resume','profile_id':users[1].id})
        await connection.post('/api/v1/admin/lock')
        own = connection.cookies.get(wall_cookie(users[1].id))
        connection.cookies.set(wall_cookie('primary'), own, path='/api/v1/user-self/wall')
        assert (await connection.get(PREFIX+'preview',params={'profile_id':'primary'})).status_code == 403
        assert (await connection.get(PREFIX+'preview',params={'profile_id':'../primary'})).status_code == 403
        assert (await connection.post(PREFIX+'timer',json={'profile_id':users[1].id,'name':'set_brightness','value':1})).status_code == 403
        assert (await connection.post('/api/v1/updates/install',json={})).status_code == 403
        assert (await connection.patch('/api/v1/settings',json={'brightness':1})).status_code == 403
        async with client(app,'192.0.2.1') as remote:
            remote.cookies.update(connection.cookies)
            assert (await remote.get(PREFIX+'access')).status_code == 403


@pytest.mark.asyncio
async def test_all_personal_timers_work_without_pin_and_do_not_replace_room_or_other_users(app_rig):
    app, users, link, _ = app_rig
    app.state.luma.update_settings({'onboarding_completed':True})
    for user in users: link(user.id)
    app.state.luma.timer.execute('start_timer',{'seconds':120,'label':'ROOM'})
    async with client(app) as connection:
        await approve_all(app,connection,users)
        for user in users:
            result = await connection.post(PREFIX+'timer',json={'profile_id':user.id,'name':'start_timer','value':{'seconds':90,'label':user.nickname+' TEA'}})
            assert result.status_code == 200 and result.json()['result']['accepted']
            assert set(result.json()['preview']) == {'profile_id','nickname','timer'}
            assert result.json()['preview']['timer']['label'] == user.nickname+' TEA'
            for other in users:
                if other.id != user.id: assert other.nickname+' TEA' not in result.text
        uid = users[1].id
        assert (await connection.post(PREFIX+'timer',json={'profile_id':uid,'name':'pause_timer'})).json()['preview']['timer']['status'] == 'paused'
        assert (await connection.post(PREFIX+'timer',json={'profile_id':uid,'name':'resume_timer'})).json()['preview']['timer']['status'] == 'running'
        assert (await connection.post(PREFIX+'timer',json={'profile_id':uid,'name':'cancel_timer'})).json()['preview']['timer']['status'] == 'idle'
        assert app.state.luma.timer.snapshot()['label'] == 'ROOM'
        for user in users:
            if user.id != uid: assert app.state.luma.personal_timers.for_user(user.id).snapshot()['status'] == 'running'


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['disconnect','phone','remove','expiry','revoke','off','forced_private','clock','update'])
async def test_revocation_or_room_suppression_denies_wall_controls_without_erasing_others(app_rig, change):
    app, users, link, _ = app_rig
    service,setup = app.state.luma,app.state.user_setup
    setup_clock = setup.clock()
    service.update_settings({'onboarding_completed':True})
    for user in users: link(user.id)
    uid = users[1].id
    async with client(app) as connection:
        await approve_all(app,connection,users)
        if change == 'disconnect': app.state.bluetooth.runtime(uid).remote_authorized.clear()
        elif change == 'phone': app.state.profiles.bind_phone(uid,'AA:BB:CC:DD:EE:99')
        elif change == 'remove': app.state.profiles.remove(uid)
        elif change == 'expiry': setup.clock = lambda: setup_clock+timedelta(days=31)
        elif change == 'revoke': setup.revoke(uid)
        elif change == 'off': service.execute(Command(CommandName.SCREEN_OFF))
        elif change == 'forced_private': service.state.forced_private = True
        elif change == 'clock': service.display_clock_trusted = lambda:False
        else: service.presence_update_busy = True
        result = await connection.post(PREFIX+'timer',json={'profile_id':uid,'name':'start_timer','value':{'seconds':90}})
        assert result.status_code == 403
        assert (await connection.get(PREFIX+'preview',params={'profile_id':uid})).status_code == 403
        if change in {'disconnect','phone','remove','revoke'}:
            assert (await connection.get(PREFIX+'preview',params={'profile_id':users[2].id})).status_code == 200


def task(app,uid,now):
    app.state.profiles.update_personal(uid,{'todo_calendar_id':'tasks','todo_completed_color_id':'5'})
    account = app.state.profile_calendars.account(uid)
    original = CalendarEvent('same_task','tasks',uid+' PRIVATE TASK',now-timedelta(days=1),now+timedelta(days=2),
        all_day=True,etag='revision',calendar_writable=True)
    account.events.append(original)
    account.google.task_write_authorized = Mock(return_value=True)
    account.google.recolor_task = Mock(return_value=replace(original,event_color_id='5',etag='new-revision'))
    return account


@pytest.mark.asyncio
async def test_shared_task_buttons_use_own_client_etag_and_completion_color(app_rig):
    app,users,link,now = app_rig
    app.state.luma.update_settings({'onboarding_completed':True})
    for user in users: link(user.id);task(app,user.id,now)
    uid = users[1].id
    async with client(app) as connection:
        await approve_all(app,connection,users)
        payload = {'profile_id':uid,'calendar_id':'tasks','event_id':'same_task','etag':'revision','completed':True}
        result = await connection.post(PREFIX+'todos/complete',json=payload)
        assert result.status_code == 200 and result.json() == {'changed':True}
        account = app.state.profile_calendars.account(uid)
        assert account.events[-1].event_color_id == '5'
        account.google.recolor_task.assert_called_once()
        for user in users:
            if user.id != uid: app.state.profile_calendars.account(user.id).google.recolor_task.assert_not_called()
        assert (await connection.post(PREFIX+'todos/complete',json=payload)).status_code == 409


@pytest.mark.asyncio
async def test_task_write_rechecks_consent_and_original_phone_session_after_lock_wait(app_rig):
    app,users,link,now = app_rig
    app.state.luma.update_settings({'onboarding_completed':True})
    uid = users[1].id;link(uid);account = task(app,uid,now)
    async with client(app) as connection:
        await approve_all(app,connection,users)
        await account.lock.acquire()
        try:
            pending = asyncio.create_task(connection.post(PREFIX+'todos/complete',json={
                'profile_id':uid,'calendar_id':'tasks','event_id':'same_task','etag':'revision','completed':True}))
            await asyncio.sleep(.1)
            link(uid)  # A new authorized session cannot revive the old request.
        finally: account.lock.release()
        assert (await pending).status_code == 403
        account.google.recolor_task.assert_not_called()
        app.state.profiles.set_setup(uid,'ready',wall_share_approved=False)
        assert (await connection.post(PREFIX+'todos/complete',json={
            'profile_id':uid,'calendar_id':'tasks','event_id':'same_task','etag':'revision','completed':True})).status_code == 403
        # No calendar sharing does not prohibit an intentional personal timer.
        assert (await connection.post(PREFIX+'timer',json={'profile_id':uid,'name':'start_timer','value':{'seconds':20}})).status_code == 200


@pytest.mark.asyncio
async def test_personal_lock_clears_only_its_grant_and_remote_restriction_preserves_wall(app_rig):
    app,users,link,_ = app_rig
    app.state.luma.update_settings({'onboarding_completed':True})
    for user in users: link(user.id)
    async with client(app) as connection:
        await approve_all(app,connection,users)
        app.state.profiles.set_remote_policy('primary_only')
        assert len((await connection.get(PREFIX+'access')).json()['users']) == 5
        assert (await connection.post(PREFIX+'lock',json={'profile_id':users[1].id})).status_code == 200
        assert (await connection.get(PREFIX+'preview',params={'profile_id':users[1].id})).status_code == 403
        assert len((await connection.get(PREFIX+'access')).json()['users']) == 4


@pytest.mark.asyncio
async def test_all_five_stored_wall_approvals_resume_only_after_new_authorization(app_rig):
    app,users,link,_ = app_rig
    app.state.luma.update_settings({'onboarding_completed':True})
    for user in users: link(user.id)
    async with client(app) as connection:
        await approve_all(app,connection,users)
        restarted = create_app(data_dir=app.state.luma.storage.path.parent)
        restarted.state.luma.display_clock_trusted=lambda:True
        async with client(restarted) as resumed:
            resumed.cookies.update(connection.cookies)
            assert (await resumed.get(PREFIX+'access')).json() == {'users':[]}
            for user in restarted.state.profiles.list():
                child = restarted.state.bluetooth.runtime(user.id)
                child.remote_authorized.begin(user.phone_address,'/new/'+user.id,'/new/source/'+user.id)
                child.remote_authorized.heartbeat(user.phone_address)
                child.service.phone_seen()
            assert len((await resumed.get(PREFIX+'access')).json()['users']) == 5
            for user in users:
                assert (await resumed.get(PREFIX+'preview',params={'profile_id':user.id})).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize('index',[0,1])
async def test_sharing_change_broadcasts_immediate_private_panel_removal(app_rig,index):
    app,users,link,_ = app_rig
    app.state.luma.update_settings({'onboarding_completed':True})
    for user in users: link(user.id)
    uid = users[index].id
    async with client(app) as connection:
        await approve_all(app,connection,users)
        queue = app.state.luma.subscribe()
        try:
            token = connection.cookies.get(wall_cookie(uid))
            result = await connection.post('/api/v1/user-self/progress',json={
                'stage':'ready','wall_share_approved':False},headers={'Cookie':f'{COOKIE}={token}'})
            assert result.status_code == 200
            assert queue.get_nowait()['type'] == 'user.settings.updated'
            snapshot = (await connection.get('/api/v1/state')).json()
            assert uid not in {panel['profile_id'] for panel in snapshot['user_panels']}
            if index == 0: assert snapshot['calendar'] == [] and snapshot['todos'] == []
        finally: app.state.luma.unsubscribe(queue)
