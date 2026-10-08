"""Synthetic Serve headers; does not sign into a tailnet or prove radio reach."""
import base64

import httpx
import pytest
from fastapi.testclient import TestClient

from luma.shortcut_gateway import create_gateway
from test_companion_api import rig, envelope, ORIGIN, IDENTITY

HEADERS={'Tailscale-User-Login':IDENTITY,'X-Forwarded-Proto':'https','Origin':ORIGIN}


@pytest.fixture
def gateway(rig):
    app=create_gateway(transport=httpx.ASGITransport(app=rig[0],client=('127.0.0.1',1234)))
    return TestClient(app,client=('127.0.0.1',5678),base_url=ORIGIN)


def test_remote_build_only_and_private_static_delivery(tmp_path):
    remote=tmp_path/'assets';remote.mkdir()
    (remote/'remote-index.html').write_text('<h1>Luma remote</h1>')
    (remote/'remote-manifest.webmanifest').write_text('{"start_url":"/remote/"}')
    (remote/'remote-index-abc123.js').write_text('/* remote only */')
    (remote/'remote-index-abc123.js.map').write_text('PRIVATE_SOURCE')
    (remote/'wall-index-abc123.js').write_text('WALL_DASHBOARD_JS')
    (tmp_path/'index.html').write_text('WALL_DASHBOARD')
    (tmp_path/'secret.txt').write_text('PRIVATE_SECRET')
    (remote/'remote-leak-abc123.js').symlink_to(tmp_path/'secret.txt')
    app=create_gateway(frontend_dir=tmp_path)
    client=TestClient(app,client=('127.0.0.1',1234),base_url=ORIGIN)
    for path in ['/remote/','/remote/assets/remote-index-abc123.js','/remote/manifest.webmanifest']:
        result=client.get(path,headers=HEADERS)
        assert result.status_code==200 and result.headers['cache-control']=='no-store'
        assert 'WALL_DASHBOARD' not in result.text
        assert "script-src 'self'" in result.headers['content-security-policy']
    for path in ['/remote/assets/remote-index-abc123.js.map','/remote/assets/remote-leak-abc123.js','/remote/assets/wall-index-abc123.js','/remote/index.html','/remote/secret.txt']:
        assert client.get(path,headers=HEADERS).status_code==404
    assert client.get('/remote/').status_code==403
    assert client.get('/remote/',headers={**HEADERS,'Tailscale-Funnel-Request':'?1'}).status_code==403
    assert client.get('/remote/assets/remote-index-abc123.js?token=secret',headers=HEADERS).status_code==403


def signed(gateway,rig,method,path,value=None,headers=None):
    proof=envelope(rig,method,path,value)
    headers={**HEADERS,'X-Luma-Device':proof['device_id'],'X-Luma-Nonce':proof['nonce'],
        'X-Luma-Proof':proof['signature'],**(headers or {})}
    if method!='GET':headers['Content-Type']='application/json'
    return gateway.request(method,path,content=base64.b64decode(proof['body']),headers=headers)


def test_signed_gateway_settings_and_preview_use_real_core_auth(gateway,rig):
    patched=signed(gateway,rig,'PATCH','/remote/api/settings',{'brightness':41,'theme':'neon-grid'})
    assert patched.status_code==200 and patched.json()['brightness']==41
    read=signed(gateway,rig,'GET','/remote/api/preview')
    assert read.status_code==200 and read.json()['settings']['theme']=='neon-grid'
    assert 'phone_address' not in read.text
    assert read.headers['cache-control']=='no-store'
    assert read.headers['referrer-policy']=='no-referrer'
    assert "frame-ancestors 'none'" in read.headers['content-security-policy']
    assert 'access-control-allow-origin' not in read.headers


@pytest.mark.parametrize('change',[{'Tailscale-User-Login':''}, {'Tailscale-User-Login':'another@example.test'},
    {'Tailscale-Funnel-Request':'?1'}, {'Origin':'https://evil.test'}, {'X-Forwarded-Proto':'http'},
    {'Host':'evil.test'}, {'X-Luma-Proof':'x'}, {'X-Luma-Nonce':'x'}])
def test_private_context_or_proof_mismatch_does_not_change_settings(gateway,rig,change):
    before=rig[0].state.luma.settings.brightness
    assert signed(gateway,rig,'PATCH','/remote/api/settings',{'brightness':12},change).status_code==403
    assert rig[0].state.luma.settings.brightness==before


def test_duplicate_headers_body_limits_and_untrusted_client_are_rejected(gateway,rig):
    duplicate=list(HEADERS.items())+[('Tailscale-User-Login',IDENTITY)]
    assert gateway.get('/remote/api/bootstrap',headers=duplicate).status_code==403
    assert gateway.get('/remote/api/bootstrap?token=secret',headers=HEADERS).status_code==403
    assert gateway.get('/remote/api/bootstrap',headers=HEADERS,params={'path':'/api/v1/settings'}).status_code==403
    assert gateway.post('/remote/api/challenge',content='x'*2049,
        headers={**HEADERS,'Content-Type':'application/json'}).status_code==413
    assert gateway.post('/remote/api/challenge',json={},headers={**HEADERS,'Content-Encoding':'gzip'}).status_code==415
    remote=TestClient(create_gateway(),client=('192.0.2.10',1),base_url=ORIGIN)
    assert remote.get('/remote/api/bootstrap',headers=HEADERS).status_code==403


def test_bootstrap_returns_only_context_and_does_not_grant_private_access(gateway):
    response=gateway.get('/remote/api/bootstrap',headers=HEADERS)
    assert response.status_code==200
    assert set(response.json())=={'origin','identityDigest'}
    assert response.json()['origin']==ORIGIN
    assert IDENTITY not in response.text
    assert gateway.get('/remote/api/preview',headers=HEADERS).status_code==403


def test_callback_is_a_fixed_no_cache_redirect_without_secret_reflection(gateway):
    response=gateway.get('/remote/google/callback?code=PRIVATE_CODE&state=wrong',headers=HEADERS,follow_redirects=False)
    assert response.status_code==303
    assert response.headers['location']=='/remote/#google=failed'
    assert response.headers['cache-control']=='no-store'
    assert response.headers['referrer-policy']=='no-referrer'
    assert 'PRIVATE_CODE' not in response.text


def test_normal_signed_catalog_burst_is_bounded_and_minute_budget_remains(monkeypatch,tmp_path):
    import luma.companion_gateway as module
    clock=[0.0];monkeypatch.setattr(module,'monotonic',lambda:clock[0])
    (tmp_path/'assets').mkdir();(tmp_path/'assets/remote-index.html').write_text('Remote entry')
    def instance():return TestClient(create_gateway(frontend_dir=tmp_path,transport=httpx.MockTransport(lambda _:httpx.Response(200,json={}))),
        client=('127.0.0.1',1),base_url=ORIGIN)
    burst=instance()
    for _ in range(24):assert burst.get('/remote/api/bootstrap',headers=HEADERS).status_code==200
    limited=burst.get('/remote/api/bootstrap',headers=HEADERS)
    assert limited.status_code==429 and limited.headers['retry-after']=='5'
    # API activity must not strand a legitimate fresh document on blank HTML.
    assert burst.get('/remote/',headers=HEADERS).status_code==200
    minute=instance()
    for index in range(180):
        clock[0]=index/3
        assert minute.get('/remote/api/bootstrap',headers=HEADERS).status_code==200
    assert minute.get('/remote/api/bootstrap',headers=HEADERS).status_code==429


@pytest.mark.parametrize('route',['/api/v1/settings','/api/v1/state','/remote/api/security/pin',
    '/remote/api/bluetooth/forget','/remote/api/backup','/remote/api/../security/lan-token'])
def test_gateway_does_not_become_a_generic_local_api_proxy(gateway,route):
    assert gateway.get(route,headers=HEADERS).status_code==404


def test_identity_origin_and_action_cannot_be_supplied_in_protocol_json(gateway):
    for extra in [{'identity':IDENTITY},{'origin':ORIGIN},{'action':'local'},{'pin':'123456'}]:
        response=gateway.post('/remote/api/challenge',json={
            'device_id':'a'*43,'method':'GET','path':'/remote/api/preview','body_digest':'0'*64,**extra},headers=HEADERS)
        assert response.status_code==422


def test_disconnect_and_revocation_fail_closed_through_gateway(gateway,rig):
    rig[0].state.bluetooth.remote_authorized.clear()
    # Build a previously valid request without requesting a new challenge.
    rig[0].state.bluetooth.remote_authorized.begin('AA:BB:CC:DD:EE:FF','/phone','/phone/source')
    rig[0].state.bluetooth.remote_authorized.heartbeat('AA:BB:CC:DD:EE:FF')
    proof=envelope(rig,'GET','/remote/api/preview')
    rig[0].state.bluetooth.remote_authorized.clear()
    response=gateway.get('/remote/api/preview',headers={**HEADERS,'X-Luma-Device':proof['device_id'],
        'X-Luma-Nonce':proof['nonce'],'X-Luma-Proof':proof['signature']})
    assert response.status_code==403 and 'calendar' not in response.text


@pytest.mark.parametrize('kind',['redirect','oversize','encoded','raw_error'])
def test_upstream_failures_are_bounded_not_reflected(kind):
    def responder(request):
        if kind=='redirect':return httpx.Response(302,headers={'Location':'https://evil.test'},json={})
        if kind=='oversize':return httpx.Response(200,content=b'x'*(1024*1024+1),headers={'Content-Type':'application/json'})
        if kind=='encoded':return httpx.Response(200,headers={'Content-Encoding':'gzip','Content-Type':'application/json'},content=b'notgzip')
        return httpx.Response(500,json={'detail':'PRIVATE_UPSTREAM_ERROR'})
    g=TestClient(create_gateway(transport=httpx.MockTransport(responder)),client=('127.0.0.1',1),base_url=ORIGIN)
    response=g.get('/remote/api/bootstrap',headers=HEADERS)
    assert response.status_code==503
    assert 'PRIVATE_UPSTREAM_ERROR' not in response.text
