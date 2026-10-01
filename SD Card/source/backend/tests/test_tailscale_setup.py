import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from luma.api import create_app
from luma.tailscale_setup import (ACTIONS, CLI, DAEMON, GATEWAY, SYSTEMCTL,
                                  TailscaleSetup, expected_serve, json_objects, validate_request)

HOST = "luma.tail12345.ts.net"
CONFIG = {"TCP": {"443": {"HTTPS": True}}, "Web": {HOST + ":443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:8743"}}}}}
AUTH = "https://login.tailscale.com/a/123456abcdef"


class FakeCommands:
    def __init__(self):
        self.calls = []
        self.active = False
        self.gateway = False
        self.state = "NeedsLogin"
        self.config = {}
        self.fail_serve = False
        self.up_output = json.dumps({"AuthURL": AUTH, "QR": "data:image/png;base64,AAAA", "BackendState": "NeedsLogin"}, indent=2)

    async def __call__(self, *args, **kwargs):
        self.calls.append(args)
        if args[0] == SYSTEMCTL:
            service = args[-1]
            if args[1] == "enable":
                if service == DAEMON: self.active = True
                if service == GATEWAY: self.gateway = True
            elif args[1] == "disable":
                if service == DAEMON: self.active = False
                if service == GATEWAY: self.gateway = False
            elif args[1] == "is-active":
                return (0 if (self.active if service == DAEMON else self.gateway) else 3), ""
            return 0, ""
        assert args[:2] == CLI
        command = args[2:]
        if command[0] == "up":
            return 1, self.up_output
        if command[0] == "status":
            return 0, json.dumps({"BackendState": self.state, "Self": {"DNSName": HOST + "."}, "User": {"private": "secret"}, "Peer": {"do-not-leak": True}})
        if command == ("serve", "reset"):
            self.config = {}
        elif command == ("serve", "status", "--json"):
            return 0, json.dumps(self.config)
        elif command[:2] == ("serve", "--bg"):
            if self.fail_serve: return 1, "secret failure details"
            self.config = copy.deepcopy(CONFIG)
        else:
            pytest.fail(f"Unexpected fixed command: {command}")
        return 0, ""


@pytest.mark.parametrize("action", sorted(ACTIONS))
def test_exact_allowed_actions(action):
    assert validate_request({"action": action}) == {"action": action}


@pytest.mark.parametrize("value", [None, [], {}, {"action": []}, {"action": "funnel"}, {"action": "up;id"}, {"action": "connect", "url": "https://attacker.example"}, {"action": "connect", "auth_key": "secret"}])
def test_rejects_free_form_privileged_input(value):
    with pytest.raises(ValueError): validate_request(value)


def test_json_stream_and_strict_proxy_shape():
    assert list(json_objects('{"a":1}\n{\n"b":2}\n')) == [{"a": 1}, {"b": 2}]
    assert expected_serve(CONFIG, HOST)
    for addition in [{"AllowFunnel": {HOST + ":443": True}}, {"Services": {}}, {"Foreground": {}}]:
        assert not expected_serve({**CONFIG, **addition}, HOST)
    bad = copy.deepcopy(CONFIG)
    bad["Web"][HOST + ":443"]["Handlers"]["/"]["Proxy"] = "http://127.0.0.1:8742"
    assert not expected_serve(bad, HOST)
    assert not expected_serve(None, HOST)


@pytest.mark.asyncio
async def test_status_never_starts_daemon_or_leaks_account():
    fake = FakeCommands()
    manager = TailscaleSetup(fake)
    assert await manager.status() == {"state": "off", "command_url": None}
    assert fake.calls == [(SYSTEMCTL, "is-active", "--quiet", DAEMON)]
    fake.active, fake.state = True, "Running"
    result = await manager.status()
    assert result == {"state": "Running", "command_url": None}
    assert "secret" not in json.dumps(result)


@pytest.mark.asyncio
async def test_enrollment_fixed_flags_and_expiring_memory_only_qr():
    fake = FakeCommands()
    clock = [10.0]
    manager = TailscaleSetup(fake, lambda: clock[0])
    result = await manager.execute({"action": "connect"})
    assert result["auth_url"] == AUTH
    up = next(c for c in fake.calls if c[:3] == (*CLI, "up"))
    assert up[3:] == ("--json", "--timeout=8s", "--hostname=luma", "--accept-dns=false", "--accept-routes=false", "--ssh=false")
    assert not fake.gateway
    clock[0] = 311
    assert "auth_url" not in await manager.status()


@pytest.mark.asyncio
async def test_foreign_auth_link_never_forwarded():
    fake = FakeCommands()
    fake.up_output = json.dumps({"AuthURL": "https://login.tailscale.com.attacker.example/a/123456", "QR": "data:image/svg+xml,secret"})
    manager = TailscaleSetup(fake)
    with pytest.raises(ValueError): await manager.execute({"action": "connect"})
    assert manager.login == {}


@pytest.mark.asyncio
async def test_running_enrollment_clears_qr():
    fake = FakeCommands()
    manager = TailscaleSetup(fake)
    await manager.execute({"action": "connect"})
    fake.state = "Running"
    assert "auth_url" not in await manager.status()


@pytest.mark.asyncio
async def test_enable_separate_after_login_and_exact_proxy_only():
    fake = FakeCommands()
    manager = TailscaleSetup(fake)
    with pytest.raises(ValueError): await manager.execute({"action": "enable"})
    fake.active, fake.state = True, "Running"
    result = await manager.execute({"action": "enable"})
    assert result["command_url"] == f"https://{HOST}/command"
    assert fake.gateway
    assert (*CLI, "serve", "--bg", "--yes", "--https=443", "http://127.0.0.1:8743") in fake.calls
    assert not any("funnel" in call or "--reset" in call for call in fake.calls)


@pytest.mark.asyncio
async def test_failed_enable_disables_gateway_without_error_leak():
    fake = FakeCommands()
    fake.active, fake.state, fake.fail_serve = True, "Running", True
    with pytest.raises(ValueError, match="Commands remain off") as error:
        await TailscaleSetup(fake).execute({"action": "enable"})
    assert "secret" not in str(error.value)
    assert not fake.gateway


@pytest.mark.asyncio
async def test_disconnect_stops_both_and_retains_identity():
    fake = FakeCommands()
    fake.active = fake.gateway = True
    manager = TailscaleSetup(fake)
    manager.login = {"auth_url": AUTH}
    assert await manager.execute({"action": "disconnect"}) == {"state": "off", "command_url": None}
    assert fake.calls == [(SYSTEMCTL, "disable", "--now", GATEWAY), (SYSTEMCTL, "disable", "--now", DAEMON)]
    assert manager.login == {}


def test_setup_api_is_physical_local_only_and_never_cacheable(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path)
    broker = AsyncMock(return_value={"state": "off", "command_url": None})
    monkeypatch.setattr("luma.api.tailscale_request", broker)
    local = TestClient(app)
    token = local.get("/api/v1/security/lan-token").json()["token"]
    remote = TestClient(app, client=("100.101.102.103", 5000))
    assert remote.post("/api/v1/tailscale", json={"action": "connect"}, headers={"X-Luma-Token": token}).status_code == 403
    assert local.post("/api/v1/tailscale", json={"action": "connect"}, headers={"Origin": "https://attacker.example"}).status_code == 403
    assert local.post("/api/v1/tailscale", json={"action": "connect", "key": "must-not-echo"}).status_code == 422
    assert local.post("/api/v1/tailscale", content=b"x" * 257).status_code == 413
    broker.assert_not_called()
    response = local.post("/api/v1/tailscale", json={"action": "status"})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"


def test_packaged_transport_is_fail_closed_dormant_and_not_userspace():
    system = Path(__file__).resolve().parents[2] / "system"
    daemon = (system / "luma-tailscaled.service").read_text()
    assert "--tun=luma-ts" in daemon and "--tun=userspace-networking" not in daemon
    assert "BindsTo=luma-tailscale-firewall.service" in daemon
    assert "StateDirectoryMode=0700" in daemon
    rules = (system / "luma-tailscale.nft").read_text()
    assert "flush ruleset" not in rules
    assert 'input iifname "luma-ts" drop' in rules
    assert 'forward iifname "luma-ts" drop' in rules
    installer = (system / "install.sh").read_text()
    boot_enable = next(line for line in installer.splitlines()
                       if line.startswith("systemctl --root=/ enable luma-api.service "))
    assert {"luma-api.service", "luma-network.socket", "luma-backup.socket",
            "luma-update.socket", "luma-tailscale-setup.socket"} <= set(boot_enable.split()[3:])
    assert "enable luma-tailscaled" not in installer
    assert "enable luma-shortcut-gateway" not in installer


def test_shortcut_token_rotation_revokes_old_token_persists_and_stays_local(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
    old = client.get("/api/v1/security/lan-token").json()["token"]
    remote = TestClient(client.app, client=("100.101.102.103", 5000))
    assert remote.post("/api/v1/security/lan-token/rotate", headers={"X-Luma-Token": old}).status_code == 403
    assert client.post("/api/v1/security/lan-token/rotate", headers={"Origin": "https://attacker.example"}).status_code == 403
    result = client.post("/api/v1/security/lan-token/rotate")
    new = result.json()["token"]
    assert old != new and len(new) == 43 and result.headers["cache-control"] == "no-store"
    assert client.post("/api/v1/shortcut-command", json={"name": "wake"}, headers={"X-Luma-Token": old}).status_code == 401
    assert client.post("/api/v1/shortcut-command", json={"name": "wake"}, headers={"X-Luma-Token": new}).status_code == 200
    restarted = TestClient(create_app(data_dir=tmp_path))
    assert restarted.get("/api/v1/security/lan-token").json()["token"] == new
