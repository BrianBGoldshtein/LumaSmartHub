"""Actual app controllers, synthetic browser keys, no phone/cloud/update install."""
import asyncio
import base64
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from luma.api import create_app
from luma.companion_auth import GRANTS_KEY, enrollment_message, request_message

ORIGIN = 'https://luma.example-tail.ts.net'
IDENTITY = 'owner@example.test'
PHONE = 'AA:BB:CC:DD:EE:FF'


def b64(raw): return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def sign(key, message):
    r, s = decode_dss_signature(key.sign(message, ec.ECDSA(hashes.SHA256())))
    return b64(r.to_bytes(32,'big') + s.to_bytes(32,'big'))


@pytest.fixture
def rig(tmp_path):
    app = create_app(data_dir=tmp_path)
    service, auth = app.state.luma, app.state.companion
    service.display_clock_trusted = lambda: True
    service.update_settings({'phone_address':PHONE})
    app.state.security.set_pin('123456')
    app.state.bluetooth.remote_authorized.begin(PHONE,'/phone','/phone/source')
    app.state.bluetooth.remote_authorized.heartbeat(PHONE)
    service.phone_seen()
    key = ec.generate_private_key(ec.SECP256R1())
    public = b64(key.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint))
    ticket = auth.issue_ticket('123456',ORIGIN)
    claim = auth.claim(ticket,ORIGIN,IDENTITY,public,sign(key,enrollment_message(ticket,ORIGIN,IDENTITY,public)))
    auth.approve('123456',claim['device_id'],claim['comparison_code'])
    app.state.admin.unlock_remote('123456', claim['device_id'], auth._phone('primary'))
    return app, key, claim['device_id']


def client(app, host='127.0.0.1'):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=(host,1234)),base_url='http://127.0.0.1:8742')


def envelope(rig, method, path, value=None, raw=None):
    app, key, device = rig
    body = raw if raw is not None else b'' if method=='GET' else json.dumps(value or {},separators=(',',':')).encode()
    nonce = app.state.companion.challenge(device,ORIGIN,IDENTITY,method,path,hashlib.sha256(body).hexdigest())['nonce']
    return {'device_id':device,'nonce':nonce,'origin':ORIGIN,'identity':IDENTITY,'method':method,
            'path':path,'body':base64.b64encode(body).decode(),
            'signature':sign(key,request_message(device,nonce,ORIGIN,IDENTITY,method,path,body))}


async def dispatch(rig, method, path, value=None, raw=None):
    payload = envelope(rig,method,path,value,raw)
    async with client(rig[0]) as c:
        return await c.post('/api/v1/companion/dispatch',json=payload)


@pytest.mark.asyncio
async def test_settings_round_trip_reuses_validation_and_never_exposes_bond_or_tokens(rig):
    app, _, _ = rig
    changed = await dispatch(rig,'PATCH','/remote/api/settings',{'theme':'hearth','brightness':38})
    assert changed.status_code==200
    assert changed.json()['theme']=='hearth'
    assert app.state.luma.settings.brightness==38
    read = await dispatch(rig,'GET','/remote/api/settings')
    assert read.headers['cache-control']=='no-store'
    assert 'phone_address' not in read.json()
    assert 'audio_output' not in read.json()
    assert 'lan_token' not in read.text
    bad = await dispatch(rig,'PATCH','/remote/api/settings',{'brightness':101})
    assert bad.status_code==422
    assert app.state.luma.settings.brightness==38


@pytest.mark.asyncio
async def test_remote_cycle_validation_reuses_wall_settings(rig):
    cycle=[{'page':'home','seconds':45},{'page':'ambient','seconds':14}]
    response=await dispatch(rig,'PATCH','/remote/api/settings',{'cycle':cycle})
    assert response.status_code==200 and response.json()['cycle']==cycle
    for value in [[],[{'page':'home','seconds':True}],[{'page':'home','seconds':4}],
                  [{'page':'unknown','seconds':30}],[{'page':'home','seconds':30,'shell':'bad'}],
                  [{'page':'home','seconds':30},{'page':'home','seconds':40}]]:
        response=await dispatch(rig,'PATCH','/remote/api/settings',{'cycle':value})
        assert response.status_code==422
        assert rig[0].state.luma.settings.cycle==cycle


@pytest.mark.asyncio
@pytest.mark.parametrize('value',[{'phone_address':None},{'audio_output':'arbitrary'},
    {'pin':'0000'},{'onboarding_completed':True},{'lan_token':'fake'}])
async def test_remote_cannot_alter_identity_auth_or_local_hardware(rig,value):
    response = await dispatch(rig,'PATCH','/remote/api/settings',value)
    assert response.status_code==422
    assert rig[0].state.luma.settings.phone_address==PHONE


@pytest.mark.asyncio
async def test_preview_and_command_results_are_projected_not_full_snapshot(rig):
    app, _, _ = rig
    # Deliberately seed future/private fields to prove projection excludes them.
    original = app.state.luma.snapshot
    def poisoned():
        value = original()
        value.update(notifications=[{'body':'PRIVATE_NOTIFICATION'}],future_secret='PRIVATE_FUTURE')
        return value
    app.state.luma.snapshot = poisoned
    for method,path,data in [('GET','/remote/api/preview',None),('POST','/remote/api/command',{'name':'set_volume','value':36})]:
        response = await dispatch(rig,method,path,data)
        assert response.status_code==200
        assert 'PRIVATE_NOTIFICATION' not in response.text and 'PRIVATE_FUTURE' not in response.text
        assert 'phone_address' not in response.text
    assert app.state.luma.settings.volume==36


@pytest.mark.asyncio
@pytest.mark.parametrize('name',['run_scene','ask','local_query','set_orientation','run_remote_scene'])
async def test_unlisted_commands_are_not_executed(rig,name):
    response = await dispatch(rig,'POST','/remote/api/command',{'name':name})
    assert response.status_code==422


@pytest.mark.asyncio
async def test_replay_body_tampering_and_revocation_block_mutation(rig):
    app, _, device = rig
    payload = envelope(rig,'PATCH','/remote/api/settings',{'brightness':23})
    async with client(app) as c:
        assert (await c.post('/api/v1/companion/dispatch',json=payload)).status_code==200
        assert (await c.post('/api/v1/companion/dispatch',json=payload)).status_code==403
        payload = envelope(rig,'PATCH','/remote/api/settings',{'brightness':24})
        payload['body']=base64.b64encode(b'{"brightness":25}').decode()
        assert (await c.post('/api/v1/companion/dispatch',json=payload)).status_code==403
        payload = envelope(rig,'PATCH','/remote/api/settings',{'brightness':26})
        app.state.companion.revoke('123456',device)
        assert (await c.post('/api/v1/companion/dispatch',json=payload)).status_code==403
    assert app.state.luma.settings.brightness==23


@pytest.mark.asyncio
async def test_disconnect_while_waiting_for_calendar_lock_prevents_settings_write(rig):
    app, _, _ = rig
    before = app.state.luma.settings.timezone
    payload = envelope(rig,'PATCH','/remote/api/settings',{'timezone':'UTC'})
    lock = app.state.google_sync_lock
    await lock.acquire()
    try:
        async with client(app) as c:
            task = asyncio.create_task(c.post('/api/v1/companion/dispatch',json=payload))
            await asyncio.sleep(.05)
            assert not task.done()
            app.state.bluetooth.remote_authorized.properties_changed('org.bluez.Device1',{'Connected':False},[])
            lock.release()
            response = await task
        assert response.status_code==403
        assert app.state.luma.settings.timezone==before
    finally:
        if lock.locked(): lock.release()


@pytest.mark.asyncio
async def test_slow_provider_result_is_not_returned_after_disconnect(rig,monkeypatch):
    app, _, _ = rig
    def provider():
        app.state.bluetooth.remote_authorized.clear()
        return [{'id':'PRIVATE_CALENDAR','summary':'Private calendar'}]
    monkeypatch.setattr(app.state.google,'list_calendars',provider)
    response = await dispatch(rig,'GET','/remote/api/google/calendars')
    assert response.status_code==403
    assert 'PRIVATE_CALENDAR' not in response.text


@pytest.mark.asyncio
async def test_local_enrollment_pin_and_serve_origin_are_not_caller_chosen(rig,monkeypatch):
    import luma.companion_api as module
    app, _, _ = rig
    status = AsyncMock(return_value={'command_url':ORIGIN+'/command'})
    monkeypatch.setattr(module,'tailscale_request',status)
    async with client(app) as c:
        bad = await c.post('/api/v1/companion/local',json={'action':'issue','pin':'111111'})
        assert bad.status_code==403
        status.assert_not_awaited()
        issued = await c.post('/api/v1/companion/local',json={'action':'issue','pin':'123456'})
        assert issued.status_code==200 and issued.json()['url'].startswith(ORIGIN+'/remote/#enroll=')
        assert issued.headers['cache-control']=='no-store'
        bad = await c.post('/api/v1/companion/local',json={'action':'issue','pin':'123456','origin':'https://evil.test'})
        assert bad.status_code==422


@pytest.mark.asyncio
@pytest.mark.parametrize('route',['local','protocol','dispatch'])
async def test_companion_internal_routes_remain_loopback_only(rig,route):
    async with client(rig[0],host='192.0.2.10') as c:
        response = await c.post('/api/v1/companion/'+route,json={})
    assert response.status_code==403


@pytest.mark.asyncio
async def test_signed_duplicate_json_is_rejected_without_echoing_private_input(rig):
    response = await dispatch(rig,'PATCH','/remote/api/settings',raw=b'{"brightness":12,"brightness":45,"title":"PRIVATE_INPUT"}')
    assert response.status_code==422
    assert 'PRIVATE_INPUT' not in response.text


def test_phone_selection_change_atomically_revokes_grants_even_if_selected_back(rig):
    app, _, _ = rig
    storage=app.state.companion.storage
    assert storage.get_secret(GRANTS_KEY)
    app.state.luma.update_settings({'phone_address':'11:22:33:44:55:66'})
    app.state.luma.update_settings({'phone_address':PHONE})
    assert storage.get_secret(GRANTS_KEY) is None
