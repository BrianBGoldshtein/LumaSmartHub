from datetime import UTC, datetime, timedelta
from threading import Event
import time
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from luma.api import create_app
from luma.models import CalendarEvent
from luma.shortcut_gateway import UPSTREAM, create_gateway, main


@pytest.fixture
def hub(tmp_path):
    app = create_app(data_dir=tmp_path)
    token = app.state.security.get_or_create_lan_token()
    gateway = create_gateway(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1234)))
    return app, TestClient(gateway), {"X-Luma-Token": token}


def test_loopback_is_not_shortcut_authentication(hub):
    app, gateway, headers = hub
    local = TestClient(app)
    for client, path in [(local, "/api/v1/shortcut-command"), (gateway, "/command")]:
        for auth in [{}, {"X-Luma-Token": "x" * 43}, {"X-Luma-Token": "invalid"}]:
            assert client.post(path, json={"name": "good_night"}, headers=auth).status_code == 401
    assert app.state.luma.settings.brightness == 70
    assert not app.state.luma.state.phone_connected


@pytest.mark.parametrize("payload", [
    {"name": "set_volume", "value": True}, {"name": "set_volume", "value": "50"},
    {"name": "set_brightness", "value": 1.5}, {"name": "set_brightness", "value": 101},
    {"name": "set_brightness", "value": -1}, {"name": "good_night", "value": "ignored?"},
    {"name": "set_theme", "value": "unknown"}, {"name": "show_page", "value": "setup"},
    {"name": "set_orientation", "value": "landscape"}, {"name": "ask", "value": "secret"},
    {"name": "run_remote_scene", "value": "drop-table"}, {"name": "run_remote_scene", "value": "Morning"},
    {"name": "wake", "source": "voice"}, {"name": "wake", "url": "https://example.com"},
    {"name": "unlock", "pin": "0427"}, {"name": ["wake"]}, {}, [],
])
def test_rejects_values_and_extra_authority(hub, payload):
    app, client, headers = hub
    response = client.post("/command", json=payload, headers=headers)
    assert response.status_code == 422
    assert response.json() == {"detail": "Unsupported command or value."}
    assert app.state.luma.settings.brightness == 70


@pytest.mark.parametrize("body", [
    b'{"name":"wake","name":"good_night"}', b'{"name":"set_volume","value":NaN}',
    b'{"name":"set_volume","value":Infinity}', b'\xff', b'{',
])
def test_invalid_json_is_not_echoed(hub, body):
    _, client, headers = hub
    response = client.post("/command", content=body, headers={**headers, "Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json() == {"detail": "Unsupported command or value."}


def test_no_setup_account_or_snapshot_routes_exist(hub):
    _, client, headers = hub
    for path in ["/", "/docs", "/openapi.json", "/api/v1/settings", "/api/v1/state",
                 "/api/v1/security/lan-token", "/api/v1/security/unlock", "/command/"]:
        assert client.get(path, headers=headers).status_code == 404
    assert client.get("/command", headers=headers).status_code == 405
    assert client.options("/command", headers=headers).status_code == 405
    assert client.post("/command?token=hidden", headers=headers, json={"name": "wake"}).status_code == 403
    assert client.post("/command", headers={**headers, "Origin": "http://127.0.0.1"}, json={"name": "wake"}).status_code == 403


def test_body_and_header_limits(hub):
    _, client, headers = hub
    response = client.post("/command", content="x" * 1025, headers={**headers, "Content-Type": "application/json"})
    assert response.status_code == 413
    assert client.post("/command", content="name=wake", headers=headers).status_code == 415
    assert client.post("/command", json={"name": "wake"}, headers={**headers, "Content-Encoding": "gzip"}).status_code == 415
    duplicate = [("X-Luma-Token", headers["X-Luma-Token"])] * 2
    assert client.post("/command", json={"name": "wake"}, headers=duplicate).status_code == 401


def test_real_command_persists_and_returns_only_acknowledgement(hub):
    app, client, headers = hub
    response = client.post("/command", json={"name": "set_theme", "value": "hearth"}, headers=headers)
    assert response.status_code == 200
    assert response.json() == {"accepted": True, "message": "Theme changed to hearth."}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert app.state.luma.storage.load_settings().theme == "hearth"
    assert not app.state.luma.state.phone_connected


def test_remote_scene_is_rejected_until_separately_allowlisted_then_acknowledged(hub):
    import asyncio
    from threading import Event

    app, client, headers = hub
    runtime = app.state.scene_runtime
    app.state.luma.display_clock_trusted = lambda: True
    runtime.trusted = lambda: True
    runtime.store.definitions['night'] = {'enabled': True, 'automatic': False, 'actions': [
        {'device': 'fan_1', 'action': 'oscillate_off', 'value': None, 'binding': 'a' * 64}]}
    runtime.configuration = lambda: {'definitions': {'night': {'needs_review': False}}}
    started = Event()

    async def remote(key):
        assert key == 'night'
        started.set()
        await asyncio.sleep(0)

    runtime.remote = remote
    payload = {'name': 'run_remote_scene', 'value': 'night'}
    denied = client.post('/command', json=payload, headers=headers)
    assert denied.status_code == 200 and not denied.json()['accepted']
    assert not started.is_set()
    runtime.remote_policy.effective = lambda key, definition: True
    allowed = client.post('/command', json=payload, headers=headers)
    assert allowed.status_code == 200 and allowed.json()['accepted']
    assert 'snapshot' not in allowed.json() and started.wait(2)


def test_remote_allowlist_is_touch_opt_in_for_exact_scene_and_dispatches_without_presence(tmp_path):
    from test_fans import RAW, configure, observed
    from luma.ir_protocol import send_result

    app=create_app(data_dir=tmp_path);service=app.state.luma;service.display_clock_trusted=lambda:True
    configure(service.fans);observed(service.fans);observed(service.fans);observed(service.fans,'fan_2')
    service.fans.learned('fan_1','power_on',RAW,revision=service.fans.revision,generation=service.fans.generation)
    observed(service.fans,key='power_on');observed(service.fans,key='power_on')
    client=TestClient(app);runtime=app.state.scene_runtime
    config=client.get('/api/v1/scenes').json()
    action=config['devices'][0]['actions'][0].copy();action.pop('label')
    saved=client.put('/api/v1/scenes/night',json={'revision':config['revision'],'enabled':True,'automatic':False,'actions':[action]})
    assert saved.status_code==200
    untouched=app.state.security.get_or_create_lan_token()
    remote=TestClient(create_gateway(transport=httpx.ASGITransport(app=app,client=('127.0.0.1',1234))))
    headers={'X-Luma-Token':untouched}
    payload={'name':'run_remote_scene','value':'night'}
    assert not remote.post('/command',json=payload,headers=headers).json()['accepted']
    fresh=client.get('/api/v1/scenes').json()
    granted=client.put('/api/v1/scenes/remote',json={'revision':fresh['remote']['revision'],'enabled':True,'scenes':['night']})
    assert granted.status_code==200 and granted.json()['remote']['scenes']['night']['allowed']
    sent=Event()
    async def transmit(*args,**kwargs):
        sent.set()
        return send_result('sent_unconfirmed')
    app.state.fan_runtime.transport=transmit
    result=remote.post('/command',json=payload,headers=headers)
    assert result.status_code==200 and result.json()['accepted'] and sent.wait(3)
    deadline=time.monotonic()+3
    while not runtime.store.runs and time.monotonic()<deadline: time.sleep(.01)
    assert runtime.store.runs[-1]['source']=='remote'
    assert runtime.store.runs[-1]['steps'][0]['action']==action
    assert service.state.phone_connected is False and service.snapshot()['privacy_redacted']
    changed=client.get('/api/v1/scenes').json()
    action2=next(item.copy() for device in changed['devices'] for item in device['actions'] if item['action']!=action['action'])
    action2.pop('label')
    changed_scene=client.put('/api/v1/scenes/night',json={'revision':changed['revision'],'enabled':True,'automatic':False,'actions':[action2]})
    assert changed_scene.status_code==200 and changed_scene.json()['remote']['scenes']['night']['needs_review']
    denied=remote.post('/command',json=payload,headers=headers)
    assert denied.status_code==200 and not denied.json()['accepted']


def test_briefing_respects_actual_presence_and_its_expiry(hub):
    app, client, headers = hub
    service = app.state.luma
    now = datetime.now(UTC)
    service.update_settings({"visible_calendar_ids": ["primary"]})
    service.replace_events([CalendarEvent("1", "primary", "Private appointment", now, now + timedelta(hours=1))])
    def briefing():
        response = client.post("/command", json={"name": "good_morning"}, headers=headers)
        assert response.status_code == 200
        assert set(response.json()) == {"accepted", "message"}
        return response.json()["message"]
    assert "Private appointment" not in briefing()
    assert not service.state.phone_connected
    service.phone_seen(now)
    assert "Private appointment" in briefing()
    service.phone_seen(now - timedelta(minutes=5))
    service.phone_disconnected(now - timedelta(minutes=5))
    assert "Private appointment" not in briefing()


def test_expired_pin_does_not_authorize_a_remote_briefing(hub):
    app, client, headers = hub
    service = app.state.luma
    service.unlock_with_pin(datetime.now(UTC) - timedelta(hours=1))
    response = client.post("/command", json={"name": "good_morning"}, headers=headers)
    assert response.status_code == 200
    assert "Your calendar is private" in response.json()["message"]


@pytest.mark.asyncio
async def test_body_limit_is_enforced_without_trusting_content_length(hub):
    app, _, headers = hub
    gateway = create_gateway(transport=httpx.ASGITransport(app=app))
    async def chunks():
        yield b" " * 600
        yield b" " * 600
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://testserver") as client:
        response = await client.post("/command", content=chunks(), headers={**headers, "Content-Type": "application/json"})
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_slow_body_has_an_absolute_deadline():
    import asyncio
    from fastapi import HTTPException
    from starlette.requests import Request
    from luma.shortcut_protocol import read_command
    async def receive():
        await asyncio.sleep(10)
        return {"type": "http.request", "body": b"{}", "more_body": False}
    request = Request({"type": "http", "headers": [(b"content-type", b"application/json")]}, receive)
    with pytest.raises(HTTPException) as error:
        await read_command(request)
    assert error.value.status_code == 408


def test_errors_and_redirects_cannot_escape_fixed_upstream():
    for status, payload in [(302, {}), (500, {"secret": "not returned"}),
                             (200, {"accepted": True, "message": "ok", "snapshot": {}}),
                             (200, {"accepted": True, "message": "x" * 9000})]:
        calls = []
        def handle(request):
            calls.append(request)
            return httpx.Response(status, json=payload, headers={"Location": "https://example.com"})
        client = TestClient(create_gateway(transport=httpx.MockTransport(handle)))
        response = client.post("/command", json={"name": "wake"},
                               headers={"X-Luma-Token": "x" * 43, "X-Forwarded-Host": "example.com", "Cookie": "secret"})
        assert response.status_code == 503
        assert response.json() == {"detail": "Hub command unavailable."}
        assert len(calls) == 1 and str(calls[0].url) == UPSTREAM
        assert "cookie" not in calls[0].headers and "x-forwarded-host" not in calls[0].headers


def test_rate_limit_does_not_trust_forwarded_addresses(hub):
    _, client, headers = hub
    with patch("luma.shortcut_gateway.monotonic", return_value=100):
        for i in range(6):
            assert client.post("/command", json={"name": "show_volume"}, headers=headers).status_code == 200
        response = client.post("/command", json={"name": "show_volume"}, headers={**headers, "X-Forwarded-For": "127.0.0.2"})
        assert response.status_code == 429 and response.headers["Retry-After"] == "60"
    with patch("luma.shortcut_gateway.monotonic", return_value=161):
        assert client.post("/command", json={"name": "show_volume"}, headers=headers).status_code == 200


def test_launcher_is_fixed_loopback_with_no_proxy_trust_or_request_logs():
    with patch("luma.shortcut_gateway.uvicorn.run") as run:
        main()
    assert run.call_args.kwargs["host"] == "127.0.0.1"
    assert run.call_args.kwargs["port"] == 8743
    assert run.call_args.kwargs["proxy_headers"] is False
    assert run.call_args.kwargs["access_log"] is False
    assert run.call_args.kwargs["limit_concurrency"] == 16
