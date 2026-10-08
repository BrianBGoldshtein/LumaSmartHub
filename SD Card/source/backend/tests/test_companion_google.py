"""Synthetic OAuth transport and real browser grant; no live Google consent."""
import json
from types import SimpleNamespace
from urllib.parse import urlencode,parse_qs,urlsplit
from unittest.mock import MagicMock

import pytest
from luma.companion_google import CompanionGoogle,WEB_CLIENT_KEY,AUTH_URI,TOKEN_URI,CALLBACK
from luma.companion_auth import CompanionDenied
from luma.integrations.google_calendar import CALENDAR_SCOPE,TASK_WRITE_SCOPE,TOKEN_KEY,CLIENT_CONFIG_KEY,OAUTH_STATE_KEY
from test_companion_api import rig,dispatch,client,ORIGIN,IDENTITY


def web_client():
    return {'web':{'client_id':'1234567890-fake.apps.googleusercontent.com','client_secret':'fake-web-secret',
                  'auth_uri':AUTH_URI,'token_uri':TOKEN_URI,'redirect_uris':[ORIGIN+CALLBACK]}}


@pytest.fixture
def remote_google(rig):
    app,key,device=rig
    storage=app.state.companion.storage
    storage.set_secret(TOKEN_KEY,'OLD_TOKENS')
    storage.set_secret(CLIENT_CONFIG_KEY,'OLD_DESKTOP_CLIENT')
    storage.set_secret(OAUTH_STATE_KEY,'OLD_DESKTOP_PENDING')
    # Old tokens here are intentionally not a real credentials document.
    app.state.google.task_write_authorized=lambda:False
    flow=MagicMock()
    flow.credentials=SimpleNamespace(refresh_token='fake-refresh',scopes=[CALENDAR_SCOPE],granted_scopes=None,
        to_json=lambda:json.dumps({'token':'fake-token','refresh_token':'fake-refresh','token_uri':TOKEN_URI}))
    factory=MagicMock(return_value=flow)
    flow.authorization_url.side_effect=lambda **_:(AUTH_URI+'?'+urlencode({'state':factory.call_args.kwargs['state']}),'unused')
    clock=[100.0]
    remote=CompanionGoogle(app.state.companion,app.state.google,clock=lambda:clock[0],flow_factory=factory)
    initial=app.state.bluetooth.companion_presence()
    recheck=lambda:app.state.companion.still_authorized(device,ORIGIN,IDENTITY,initial)
    remote.set_client(web_client(),ORIGIN,recheck)
    return remote,flow,factory,clock,initial


def begin(rig,remote_google,task_updates=False):
    remote,flow,factory,_,initial=remote_google
    result=remote.begin(rig[2],ORIGIN,IDENTITY,initial,task_updates=task_updates)
    state=parse_qs(urlsplit(result['url']).query)['state'][0]
    return urlencode({'state':state,'code':'fake-code'})


def test_remote_consent_pkce_fixed_target_offline_and_one_use_commit(rig,remote_google):
    remote,flow,factory,_,_=remote_google
    query=begin(rig,remote_google)
    assert factory.call_args.kwargs['autogenerate_code_verifier'] is False
    assert len(factory.call_args.kwargs['code_verifier'])>=43
    assert flow.authorization_url.call_args.kwargs=={'access_type':'offline','prompt':'consent','include_granted_scopes':'true'}
    assert flow.redirect_uri==ORIGIN+CALLBACK
    remote.finish(ORIGIN,IDENTITY,query)
    assert flow.oauth2session.trust_env is False
    assert flow.fetch_token.call_args.kwargs=={'code':'fake-code','timeout':15}
    storage=remote.storage
    assert json.loads(storage.get_secret(TOKEN_KEY))['refresh_token']=='fake-refresh'
    assert storage.get_secret(CLIENT_CONFIG_KEY)=='OLD_DESKTOP_CLIENT'
    assert storage.get_secret(OAUTH_STATE_KEY)=='OLD_DESKTOP_PENDING'
    with pytest.raises(ValueError):remote.finish(ORIGIN,IDENTITY,query)
    assert flow.fetch_token.call_count==1


@pytest.mark.parametrize('change',['disconnect','revoke','session','expired','denied','duplicate','exchange_failure','missing_refresh','missing_scope','configuration'])
def test_failed_remote_consent_keeps_existing_tokens(rig,remote_google,change):
    remote,flow,_,clock,_=remote_google
    query=begin(rig,remote_google,task_updates=change=='missing_scope')
    app=rig[0]
    if change=='disconnect':app.state.bluetooth.remote_authorized.clear()
    if change=='revoke':app.state.companion.revoke('123456',rig[2])
    if change=='session':app.state.bluetooth.remote_authorized.begin('AA:BB:CC:DD:EE:FF','/new','/new/source');app.state.bluetooth.remote_authorized.heartbeat('AA:BB:CC:DD:EE:FF')
    if change=='expired':clock[0]+=901
    if change=='denied':query+='&error=access_denied'
    if change=='duplicate':query+='&code=other'
    if change=='exchange_failure':flow.fetch_token.side_effect=OSError('PRIVATE_PROVIDER_DATA')
    if change=='missing_refresh':flow.credentials.refresh_token=None
    if change=='configuration':flow.fetch_token.side_effect=lambda **_:remote.storage.set_secret(WEB_CLIENT_KEY,'{}')
    with pytest.raises((ValueError,OSError)):remote.finish(ORIGIN,IDENTITY,query)
    assert remote.storage.get_secret(TOKEN_KEY)=='OLD_TOKENS'
    with pytest.raises(ValueError):remote.finish(ORIGIN,IDENTITY,query)


def test_disconnect_during_provider_exchange_prevents_token_commit(rig,remote_google):
    remote,flow,_,_,_=remote_google;query=begin(rig,remote_google)
    flow.fetch_token.side_effect=lambda **_:rig[0].state.bluetooth.remote_authorized.clear()
    with pytest.raises(CompanionDenied):remote.finish(ORIGIN,IDENTITY,query)
    assert remote.storage.get_secret(TOKEN_KEY)=='OLD_TOKENS'


def test_cancelling_pending_also_prevents_inflight_primary_consent_commit(rig,remote_google):
    remote,flow,_,_,_=remote_google
    query=begin(rig,remote_google)
    flow.fetch_token.side_effect=lambda **_:remote.cancel_pending()
    with pytest.raises(ValueError):remote.finish(ORIGIN,IDENTITY,query)
    assert remote.storage.get_secret(TOKEN_KEY)=='OLD_TOKENS'
    assert remote.pending=={}


def test_wrong_identity_does_not_consume_matching_owner_attempt(rig,remote_google):
    remote,flow,_,_,_=remote_google;query=begin(rig,remote_google)
    with pytest.raises(ValueError):remote.finish(ORIGIN,'other@example.test',query)
    flow.fetch_token.assert_not_called()
    remote.finish(ORIGIN,IDENTITY,query)


@pytest.mark.parametrize('kind',['installed','callback','auth_uri','token_uri','secret','client'])
def test_web_configuration_is_normalized_and_cannot_select_network_targets(rig,remote_google,kind):
    remote,_,_,_,initial=remote_google;config=web_client()
    if kind=='installed':config={'installed':config['web']}
    if kind=='callback':config['web']['redirect_uris']=['https://evil.test/callback']
    if kind=='auth_uri':config['web']['auth_uri']='https://evil.test/auth'
    if kind=='token_uri':config['web']['token_uri']='http://127.0.0.1:8742/api/v1/settings'
    if kind=='secret':config['web']['client_secret']='bad\nsecret'
    if kind=='client':config['web']['client_id']='arbitrary'
    old=remote.storage.get_secret(WEB_CLIENT_KEY)
    with pytest.raises(ValueError):remote.set_client(config,ORIGIN,lambda:None)
    assert remote.storage.get_secret(WEB_CLIENT_KEY)==old


@pytest.mark.asyncio
async def test_signed_web_setup_status_and_callback_result_do_not_export_secrets(rig):
    uploaded=await dispatch(rig,'POST','/remote/api/google/web-client',web_client())
    assert uploaded.status_code==200 and uploaded.json()['web_configured']
    assert 'fake-web-secret' not in uploaded.text
    status=await dispatch(rig,'GET','/remote/api/google/status')
    assert status.status_code==200 and status.json()['redirect_uri']==ORIGIN+CALLBACK
    assert 'client_secret' not in status.text
    consent=await dispatch(rig,'POST','/remote/api/google/authorize',{'task_updates':False})
    assert consent.status_code==200
    assert urlsplit(consent.json()['url']).netloc=='accounts.google.com'
    assert 'code_challenge=' in consent.json()['url']
    # Unknown callback cannot alter the previously stored grant.
    storage=rig[0].state.companion.storage;storage.set_secret(TOKEN_KEY,'OLD_TOKEN')
    async with client(rig[0]) as c:
        response=await c.post('/api/v1/companion/google-callback',json={'origin':ORIGIN,'identity':IDENTITY,'query':'state=wrong&code=PRIVATE_CODE'})
    assert response.json()=={'connected':False} and 'PRIVATE_CODE' not in response.text
    assert storage.get_secret(TOKEN_KEY)=='OLD_TOKEN'


@pytest.mark.asyncio
async def test_callback_internal_route_is_not_public(rig):
    async with client(rig[0],host='192.0.2.11') as c:
        response=await c.post('/api/v1/companion/google-callback',json={})
    assert response.status_code==403
