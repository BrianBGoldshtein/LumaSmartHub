from pathlib import Path
from unittest.mock import Mock

from fastapi.testclient import TestClient

from luma.api import create_app
from luma.portal import PORTAL_PROBE, PortalBrowser


def test_portal_browser_is_user_launched_and_keeps_security_and_address_bar(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    launcher = Mock()
    launcher.return_value.poll.return_value = None
    portal = PortalBrowser(launcher)
    launcher.assert_not_called()
    portal.open("request-1")
    portal.open("request-1")
    portal.open("request-2")
    launcher.assert_called_once()
    args = launcher.call_args.args[0]
    assert args[-1] == PORTAL_PROBE
    assert "--kiosk" not in args and "--no-sandbox" not in args
    assert not any("ignore-certificate" in arg or "--app=" in arg for arg in args)
    assert any("luma-portal" in arg for arg in args)
    launcher.return_value.poll.return_value = 0
    portal.open("request-3")
    assert launcher.call_count == 2


def test_portal_requests_require_live_desktop_and_expire(tmp_path, monkeypatch):
    client = TestClient(create_app(data_dir=tmp_path))
    monkeypatch.setattr("luma.api.monotonic", lambda: 100)
    assert client.post("/api/v1/network/portal").status_code == 503
    client.post("/api/v1/device/report", json={"controls": {}})
    assert client.post("/api/v1/network/portal").status_code == 200
    assert client.get("/api/v1/network/portal-request").json()["id"]
    monkeypatch.setattr("luma.api.monotonic", lambda: 131)
    assert client.get("/api/v1/network/portal-request").json()["id"] is None


def test_portal_is_never_controllable_from_the_lan(tmp_path):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app, client=("192.168.1.9", 4000))
    headers = {"X-Luma-Token": app.state.security.get_or_create_lan_token()}
    assert client.post("/api/v1/network/portal", headers=headers).status_code == 403
    assert client.get("/api/v1/network/portal-request", headers=headers).status_code == 403
