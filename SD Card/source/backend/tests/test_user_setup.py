"""Actual own-account/local controllers with synthetic phones and OAuth only."""
import asyncio
from datetime import timedelta
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from luma.api import create_app
from luma.companion_auth import CompanionDenied
from luma.companion_google import AUTH_URI, TOKEN_URI
from luma.integrations.google_calendar import CALENDAR_SCOPE, CLIENT_CONFIG_KEY, TOKEN_KEY
from luma.user_setup import COOKIE, GRANT_KEY, DRAFT_SECONDS, BOUND_SECONDS, SetupDenied
from luma.user_setup_google import UserSetupGoogle
from test_companion_api import client, ORIGIN, IDENTITY, b64, sign
from test_multiuser_app import app_rig
from test_pairing import FakeDriver, DEVICE, ADDRESS, until
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from luma.companion_auth import enrollment_message


async def manage(connection, action, uid=None, name=None):
    payload = {'action':action}
    if uid is not None: payload['profile_id'] = uid
    if name is not None: payload['nickname'] = name
    return await connection.post('/api/v1/users/manage', json=payload)


@pytest.mark.asyncio
async def test_create_requires_actual_primary_pin_and_returns_no_secret_body(tmp_path):
    app = create_app(data_dir=tmp_path)
    async with client(app) as connection:
        assert (await manage(connection,'create',name='Alex')).status_code == 409
        app.state.security.set_pin('123456')
        assert (await manage(connection,'create',name='Alex')).status_code == 403
        await connection.post('/api/v1/admin/unlock',json={'pin':'123456'})
        result = await manage(connection,'create',name='Alex')
        assert result.status_code == 200 and result.json()['approved']
        assert 'HttpOnly' in result.headers['set-cookie'] and 'SameSite=strict' in result.headers['set-cookie']
        assert 'Path=/api/v1/user-self' in result.headers['set-cookie']
        token = connection.cookies.get(COOKIE)
        assert token not in result.text
        uid = result.json()['profile_id']
        stored = app.state.profiles.account_storage(uid).get_secret(GRANT_KEY)
        assert token not in stored and 'digest' in stored
        await connection.post('/api/v1/admin/lock')
        status = await connection.get('/api/v1/user-self/status')
        assert status.status_code == 200 and status.json()['nickname'] == 'Alex'
        assert not status.json()['phone_registered']
        assert (await connection.get('/api/v1/users')).status_code == 403
        assert (await connection.patch('/api/v1/settings',json={'brightness':1})).status_code == 403
        assert (await connection.patch('/api/v1/user-self/settings',json={'visible_calendar_ids':['private']})).status_code == 403
        assert (await connection.get('/api/v1/user-self/preview')).status_code == 403


@pytest.mark.asyncio
async def test_paired_guest_resumes_without_primary_and_cannot_choose_another_account(app_rig):
    app, users, link, _ = app_rig
    app.state.security.set_pin('123456')
    uid = users[1].id
    link(uid)
    async with client(app) as connection:
        await connection.post('/api/v1/admin/unlock',json={'pin':'123456'})
        assert (await manage(connection,'resume',uid)).status_code == 200
        await connection.post('/api/v1/admin/lock')
        result = await connection.patch('/api/v1/user-self/settings',json={'visible_calendar_ids':['alex-only']})
        assert result.status_code == 200
        assert app.state.profiles.get(uid).personal['visible_calendar_ids'] == ['alex-only']
        assert app.state.profiles.get('primary').personal['visible_calendar_ids'] == ['events']
        assert (await connection.patch('/api/v1/user-self/settings',json={'profile_id':'primary'})).status_code == 403
        assert (await connection.patch('/api/v1/user-self/settings',json={'sleep_calendar_ids':['private']})).status_code == 403
        assert (await connection.post('/api/v1/user-self/timer',json={'name':'start_timer','value':{'seconds':90,'label':'Alex tea'}})).status_code == 200
        assert app.state.luma.personal_timers.for_user(uid).snapshot()['label'] == 'Alex tea'
        assert app.state.luma.timer.snapshot()['status'] == 'idle'
        assert (await connection.post('/api/v1/user-self/timer',json={'name':'set_brightness','value':5})).status_code == 403
        progress = await connection.post('/api/v1/user-self/progress',json={'stage':'calendars','wall_share_approved':True})
        assert progress.status_code == 200 and progress.json()['setup_stage'] == 'calendars'
        app.state.bluetooth.runtime(uid).remote_authorized.clear()
        assert (await connection.get('/api/v1/user-self/status')).status_code == 403
        assert (await connection.get('/api/v1/user-self/preview')).status_code == 403
        link(uid)
        assert (await connection.get('/api/v1/user-self/status')).json()['setup_stage'] == 'calendars'
        # Stored approval may survive an application restart, but cannot create
        # presence. New runtime must establish its own actual ANCS generation.
        restarted = create_app(data_dir=app.state.luma.storage.path.parent)
        token = connection.cookies.get(COOKIE)
        assert token not in app.state.profiles.account_storage(uid).get_secret(GRANT_KEY)
        async with client(restarted) as new_connection:
            new_connection.cookies.set(COOKIE,token,path='/api/v1/user-self')
            assert (await new_connection.get('/api/v1/user-self/status')).status_code == 403
            child = restarted.state.bluetooth.runtime(uid)
            child.remote_authorized.begin(users[1].phone_address or app.state.profiles.get(uid).phone_address,'/new','/new/source')
            child.remote_authorized.heartbeat(app.state.profiles.get(uid).phone_address)
            child.service.phone_seen()
            assert (await new_connection.get('/api/v1/user-self/status')).json()['setup_stage'] == 'calendars'


@pytest.mark.asyncio
async def test_draft_pairing_is_confirmed_for_own_phone_only_and_grant_becomes_bound(tmp_path):
    app = create_app(data_dir=tmp_path)
    app.state.security.set_pin('123456')
    driver = FakeDriver()
    setup = app.state.user_setup
    setup.pairing.driver_factory = lambda: driver
    async with client(app) as connection:
        await connection.post('/api/v1/admin/unlock',json={'pin':'123456'})
        uid = (await manage(connection,'create',name='Alex')).json()['profile_id']
        token = connection.cookies.get(COOKIE)
        await connection.post('/api/v1/admin/lock')
        started = await connection.post('/api/v1/user-self/pairing/start')
        assert started.status_code == 200
        await until(lambda: bool(setup.pairing.devices))
        assert (await connection.post('/api/v1/user-self/pairing/select',json={'session':setup.pairing.session,'device':DEVICE})).status_code == 200
        await until(lambda: setup.pairing.phase == 'confirming')
        assert not app.state.profiles.get(uid).phone_address and driver.trust_calls == 0
        assert (await connection.post('/api/v1/user-self/pairing/confirm',json={'session':setup.pairing.session,
            'challenge':setup.pairing.challenge,'accepted':True})).status_code == 200
        await setup.pairing.task
        assert setup.pairing.phase == 'complete'
        assert app.state.profiles.get(uid).phone_address == ADDRESS
        assert app.state.profiles.get('primary').phone_address is None
        assert driver.trust_calls == 1
        assert (await connection.get('/api/v1/user-self/status')).status_code == 403  # Bond is not ANCS.
        child = app.state.bluetooth.runtime(uid)
        child.remote_authorized.begin(ADDRESS,'/guest','/guest/source')
        child.remote_authorized.heartbeat(ADDRESS)
        child.service.phone_seen()
        status = await connection.get('/api/v1/user-self/status')
        assert status.status_code == 200 and status.json()['phone_authorized']
        assert connection.cookies.get(COOKIE) == token
        assert (await connection.post('/api/v1/user-self/pairing/start')).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['expired','revoked','other_phone'])
async def test_pairing_never_trusts_a_phone_after_draft_revocation(tmp_path,change):
    app = create_app(data_dir=tmp_path)
    user = app.state.profiles.create_secondary('Alex')
    setup = app.state.user_setup
    driver = FakeDriver()
    setup.pairing.driver_factory = lambda: driver
    token, _ = setup.issue(user.id,'http://127.0.0.1:8742')
    setup.start_pairing(token,'http://127.0.0.1:8742')
    await until(lambda: bool(setup.pairing.devices))
    if change == 'expired':
        initial = setup.clock()
        setup.clock = lambda: initial+timedelta(seconds=DRAFT_SECONDS+1)
    if change == 'revoked': setup.revoke(user.id)
    if change == 'other_phone': app.state.profiles.bind_phone('primary',ADDRESS)
    setup.pairing.select(setup.pairing.session,DEVICE)
    await setup.pairing.task
    assert setup.pairing.phase == 'error' and driver.pair_calls == 0 and driver.trust_calls == 0
    assert not app.state.profiles.get(user.id).phone_address


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['clear_phone','remove','restore','origin','expired','lock'])
async def test_delegation_revocation_binding_origin_and_backup_fail_closed(app_rig,tmp_path,change):
    app, users, link, _ = app_rig
    uid = users[1].id
    link(uid)
    setup = app.state.user_setup
    token, _ = setup.issue(uid,'http://127.0.0.1:8742')
    assert setup.require(token,'http://127.0.0.1:8742')[0].id == uid
    if change == 'clear_phone': app.state.profiles.bind_phone(uid,None)
    if change == 'remove': app.state.profiles.remove(uid)
    if change == 'restore':
        path = tmp_path/'copy.db'
        app.state.luma.storage.backup(path)
        app.state.luma.storage.restore(path)
    if change == 'expired':
        initial = setup.clock()
        setup.clock = lambda:initial+timedelta(seconds=BOUND_SECONDS)
    if change == 'lock': setup.revoke(uid)
    with pytest.raises(SetupDenied):
        setup.require(token,'http://localhost:8742' if change == 'origin' else 'http://127.0.0.1:8742')


@pytest.mark.asyncio
async def test_slow_personal_read_cannot_return_after_new_phone_session(app_rig):
    app, users, link, _ = app_rig
    uid = users[1].id
    link(uid)
    setup = app.state.user_setup
    token, _ = setup.issue(uid,'http://127.0.0.1:8742')
    account = app.state.profile_calendars.account(uid)
    def read():
        link(uid)
        return [{'id':'private','summary':'DO NOT EXPORT'}]
    account.google.list_calendars = Mock(side_effect=read)
    async with client(app) as connection:
        connection.cookies.set(COOKIE,token,path='/api/v1/user-self')
        result = await connection.get('/api/v1/user-self/google/calendars')
    assert result.status_code == 403 and 'DO NOT EXPORT' not in result.text


@pytest.fixture
def local_google(app_rig):
    app, users, link, _ = app_rig
    uid = users[1].id
    link(uid)
    app.state.luma.storage.set_secret(CLIENT_CONFIG_KEY,json.dumps({'installed':{
        'client_id':'1234567890-fake.apps.googleusercontent.com','client_secret':'fake-client-secret',
        'auth_uri':AUTH_URI,'token_uri':TOKEN_URI}}))
    app.state.luma.storage.set_secret(TOKEN_KEY,'PRIMARY UNCHANGED')
    setup = app.state.user_setup
    token, _ = setup.issue(uid,'http://127.0.0.1:8742')
    flow = MagicMock()
    flow.credentials = SimpleNamespace(refresh_token='fake-refresh',scopes=[CALENDAR_SCOPE],granted_scopes=None,
        to_json=lambda:json.dumps({'token':'fake-token','refresh_token':'fake-refresh'}))
    factory = MagicMock(return_value=flow)
    flow.authorization_url.side_effect = lambda **_:(AUTH_URI+'?'+urlencode({'state':factory.call_args.kwargs['state']}),'unused')
    clock = [0.0]
    desktop = setup.desktop = UserSetupGoogle(setup,clock=lambda:clock[0],flow_factory=factory)
    result = desktop.begin(token,'http://127.0.0.1:8742')
    state = parse_qs(urlsplit(result['url']).query)['state'][0]
    return app, uid, token, desktop, flow, factory, clock, urlencode({'state':state,'code':'fake-code'}), link


def test_local_google_keeps_primary_tokens_and_commits_only_own_after_pkce(local_google):
    app, uid, token, desktop, flow, factory, _, query, _ = local_google
    assert len(factory.call_args.kwargs['code_verifier']) >= 43
    assert factory.call_args.kwargs['autogenerate_code_verifier'] is False
    desktop.finish(token,'http://127.0.0.1:8742',query)
    assert flow.fetch_token.call_args.kwargs == {'code':'fake-code','timeout':15}
    assert flow.oauth2session.trust_env is False
    assert app.state.luma.storage.get_secret(TOKEN_KEY) == 'PRIMARY UNCHANGED'
    assert json.loads(app.state.profiles.account_storage(uid).get_secret(TOKEN_KEY))['refresh_token'] == 'fake-refresh'
    with pytest.raises(ValueError): desktop.finish(token,'http://127.0.0.1:8742',query)
    assert flow.fetch_token.call_count == 1


@pytest.mark.parametrize('change',['disconnect','session','revoke','remove','cancel','expired','scope','refresh','configuration','denied','duplicate','other_cookie'])
def test_local_google_late_failures_never_commit_own_credentials(local_google,change):
    app, uid, token, desktop, flow, _, clock, query, link = local_google
    store = app.state.profiles.account_storage(uid)
    store.set_secret(TOKEN_KEY,'OWN OLD TOKENS')
    def mutate(**_):
        if change == 'disconnect': app.state.bluetooth.runtime(uid).remote_authorized.clear()
        if change == 'session': link(uid)
        if change == 'revoke': app.state.user_setup.revoke(uid)
        if change == 'remove': app.state.profiles.remove(uid)
        if change == 'cancel': desktop.cancel(uid)
        if change == 'expired': clock[0] = 901
        if change == 'configuration': app.state.luma.storage.set_secret(CLIENT_CONFIG_KEY,'{}')
    flow.fetch_token.side_effect = mutate
    if change == 'scope': flow.credentials.granted_scopes = []
    if change == 'refresh': flow.credentials.refresh_token = None
    if change == 'denied': query += '&error=access_denied'
    if change == 'duplicate': query += '&code=second'
    if change == 'other_cookie': token = 'z'*43
    with pytest.raises((ValueError,SetupDenied)):
        desktop.finish(token,'http://127.0.0.1:8742',query)
    assert app.state.luma.storage.get_secret(TOKEN_KEY) == 'PRIMARY UNCHANGED'
    if change != 'remove': assert store.get_secret(TOKEN_KEY) == 'OWN OLD TOKENS'


@pytest.mark.asyncio
async def test_lan_cross_origin_and_forged_profile_header_never_select_own_setup(app_rig):
    app, users, link, _ = app_rig
    link(users[1].id)
    token, _ = app.state.user_setup.issue(users[1].id,'http://127.0.0.1:8742')
    async with client(app,'192.0.2.3') as connection:
        connection.cookies.set(COOKIE,token,path='/api/v1/user-self')
        assert (await connection.get('/api/v1/user-self/status')).status_code == 403
    async with client(app) as connection:
        assert (await connection.get('/api/v1/user-self/status',headers={'x-luma-profile':users[1].id})).status_code == 403
        connection.cookies.set(COOKIE,token,path='/api/v1/user-self')
        assert (await connection.get('/api/v1/user-self/status',headers={'Origin':'https://evil.invalid'})).status_code == 403


@pytest.mark.asyncio
async def test_primary_management_capacity_rename_and_removal_are_targeted(app_rig):
    app, users, link, _ = app_rig
    app.state.security.set_pin('123456')
    uid = users[1].id
    link(uid)
    link(users[2].id)
    setup = app.state.user_setup
    own_token, _ = setup.issue(uid,'http://127.0.0.1:8742')
    other_token, _ = setup.issue(users[2].id,'http://127.0.0.1:8742')
    own_store = app.state.profiles.account_storage(uid)
    own_store.set_secret(TOKEN_KEY,'PRIVATE OWN TOKEN')
    app.state.luma.personal_timers.for_user(uid).execute('start_timer',{'seconds':60})
    async with client(app) as connection:
        await connection.post('/api/v1/admin/unlock',json={'pin':'123456'})
        assert (await manage(connection,'create',name='Sixth')).status_code == 422
        assert (await manage(connection,'rename','primary','Brian')).status_code == 200
        assert (await manage(connection,'rename',uid,'Brian')).status_code == 422
        assert (await manage(connection,'remove','primary')).status_code == 422
        result = await manage(connection,'remove',uid)
        assert result.status_code == 200 and result.json() == {'removed':True}
    assert len(app.state.profiles.list()) == 4
    with pytest.raises(SetupDenied):setup.require(own_token,'http://127.0.0.1:8742')
    assert setup.require(other_token,'http://127.0.0.1:8742')[0].id == users[2].id
    assert app.state.luma.storage.get_secret(f'profile:{uid}:{TOKEN_KEY}') is None
    assert uid not in app.state.luma.personal_timers._timers
    assert uid not in app.state.profile_calendars.accounts
    assert app.state.bluetooth.companion_presence(users[2].id).authorized


@pytest.mark.asyncio
async def test_changing_registered_phone_hides_old_personal_choices_until_authorization(app_rig):
    app, users, link, _=app_rig
    uid=users[1].id
    link(uid)
    app.state.security.set_pin('123456')
    async with client(app) as connection:
        await connection.post('/api/v1/admin/unlock',json={'pin':'123456'})
        result=await manage(connection,'clear_phone',uid)
        assert result.status_code==200
        status=await connection.get('/api/v1/user-self/status')
        assert status.status_code==200
        assert status.json()['setup_stage']=='phone' and status.json()['personal']['visible_calendar_ids']==[]
        assert not status.json()['google']['authorized']
    assert app.state.profiles.get(uid).personal['visible_calendar_ids']==['events']


def test_google_commit_checks_revocation_inside_the_write_transaction(local_google,monkeypatch):
    app,uid,token,desktop,_,_,_,query,_=local_google
    store=app.state.profiles.account_storage(uid)
    store.set_secret(TOKEN_KEY,'OWN OLD TOKENS')
    original=app.state.user_setup.validate_commit
    def revoke_before_commit(db,*args):
        db.execute('DELETE FROM secrets WHERE key=?',(f'profile:{uid}:{GRANT_KEY}',))
        original(db,*args)
    monkeypatch.setattr(app.state.user_setup,'validate_commit',revoke_before_commit)
    with pytest.raises(SetupDenied):desktop.finish(token,'http://127.0.0.1:8742',query)
    assert store.get_secret(TOKEN_KEY)=='OWN OLD TOKENS'


@pytest.mark.asyncio
async def test_personal_phone_cannot_pair_while_primary_flow_is_running(tmp_path):
    app=create_app(data_dir=tmp_path)
    user=app.state.profiles.create_secondary('Alex')
    setup=app.state.user_setup
    token,_=setup.issue(user.id,'http://127.0.0.1:8742')
    app.state.pairing.driver_factory=lambda:FakeDriver()
    app.state.pairing.start()
    try:
        from luma.profiles import ProfileError
        with pytest.raises(ProfileError,match='other pairing'):
            setup.start_pairing(token,'http://127.0.0.1:8742')
    finally:
        await app.state.pairing.close()


def test_delegated_browser_enrollment_never_selects_another_user_or_bypasses_policy(app_rig):
    app,users,link,_=app_rig
    uid=users[1].id
    link(uid);link(users[2].id)
    setup=app.state.user_setup
    token,_=setup.issue(uid,'http://127.0.0.1:8742')
    _,check=setup.recheck(token,'http://127.0.0.1:8742')
    auth=app.state.companion
    with setup.lock:
        ticket=auth.issue_for_setup(ORIGIN,uid,check)
    key=ec.generate_private_key(ec.SECP256R1())
    public=b64(key.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint))
    claim=auth.claim(ticket,ORIGIN,IDENTITY,public,sign(key,enrollment_message(ticket,ORIGIN,IDENTITY,public)))
    other_token,_=setup.issue(users[2].id,'http://127.0.0.1:8742')
    _,other_check=setup.recheck(other_token,'http://127.0.0.1:8742')
    with setup.lock:
        assert auth.pending_for_setup(users[2].id,other_check) is None
        with pytest.raises(CompanionDenied):
            auth.approve_for_setup(users[2].id,claim['device_id'],claim['comparison_code'],other_check)
        with pytest.raises(CompanionDenied,match='other user'):
            auth.issue_for_setup(ORIGIN,users[2].id,other_check)
        auth.approve_for_setup(uid,claim['device_id'],claim['comparison_code'],check)
    row=auth._grants()[claim['device_id']]
    assert row['profile_id']==uid and row['phone']==app.state.profiles.get(uid).phone_address
    app.state.profiles.set_remote_policy('primary_only')
    with setup.lock,pytest.raises(CompanionDenied):auth.issue_for_setup(ORIGIN,uid,check)
    assert setup.require(token,'http://127.0.0.1:8742')[0].id==uid  # Wall setup/timer survives the remote fallback.
