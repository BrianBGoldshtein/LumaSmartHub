import asyncio
import json
import os
from pathlib import Path
import socket
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from luma.api import create_app
from luma.pi_connect_setup import ACTION_SET, CLI, PiConnectSetup, parse_status, validate_request
import luma.pi_connect_setup as pi_connect_module

VERIFY = "https://connect.raspberrypi.com/verify/ABCD-EFGH"


class FakePiConnect:
    def __init__(self):
        self.calls = []
        self.signed_in = False
        self.shell = False
        self.signin_output = f"Complete sign in by visiting {VERIFY}".encode()

    async def __call__(self, *args, timeout=15, input_data=None):
        self.calls.append((args, input_data))
        command = args[1:]
        if command == ("status",):
            return 0, ("Signed in: " + ("yes" if self.signed_in else "no") + "\n"
                       "Remote shell: " + ("allowed" if self.shell else "disabled") + " (0 sessions active)\n").encode()
        if command == ("on",) or command == ("vnc", "off"):
            return 0, b""
        if command == ("signin",):
            return 0, self.signin_output
        if command == ("shell", "on"):
            self.shell = True
            return 0, b""
        if command == ("shell", "off"):
            self.shell = False
            return 0, b""
        pytest.fail(f"Unexpected fixed Pi Connect command: {command}")


@pytest.mark.parametrize("action", sorted(ACTION_SET))
def test_request_vocabulary_is_exact(action):
    assert validate_request({"action": action}) == {"action": action}


@pytest.mark.parametrize("value", [None, [], {}, {"action": []}, {"action": "run"},
                                     {"action": "shell_on", "command": "sudo id"},
                                     {"action": "signin", "auth_key": "private"}])
def test_rejects_extra_or_arbitrary_request_data(value):
    with pytest.raises(ValueError):
        validate_request(value)


def test_status_parser_returns_only_link_and_remote_shell_state():
    assert parse_status(b"Signed in: yes\nRemote shell: allowed (0 sessions active)\n") == {
        "available": True, "state": "remote_shell_enabled", "signed_in": True, "remote_shell": True}
    assert parse_status(b"Signed in: yes\nRemote shell: disabled (0 sessions active)\n")["remote_shell"] is False
    assert parse_status(b"Raspberry Pi Connect is not running")["state"] == "off"
    assert "secret-account" not in json.dumps(parse_status(b"Signed in: no\nUser: secret-account\n"))


@pytest.mark.asyncio
async def test_signin_starts_connect_but_keeps_remote_shell_off_and_qr_local():
    fake = FakePiConnect()
    qr_urls = []

    async def local_qr(url):
        qr_urls.append(url)
        return "data:image/png;base64,LOCAL"

    setup = PiConnectSetup(fake, local_qr, lambda: 20.0, installed=lambda: True)
    result = await setup.execute({"action": "signin"})
    assert result["state"] == "awaiting_approval"
    assert result["verification_url"] == VERIFY and result["qr"] == "data:image/png;base64,LOCAL"
    assert qr_urls == [VERIFY]
    assert [call[0][1:] for call in fake.calls] == [("on",), ("vnc", "off"), ("shell", "off"), ("signin",), ("status",)]
    assert not fake.shell
    assert (await setup.execute({"action": "status"}))["verification_url"] == VERIFY


@pytest.mark.asyncio
async def test_untrusted_verification_url_is_never_shown():
    fake = FakePiConnect()
    fake.signin_output = b"https://connect.raspberrypi.com.attacker.example/verify/ABCD-EFGH"
    setup = PiConnectSetup(fake, installed=lambda: True)
    with pytest.raises(ValueError, match="No verification link"):
        await setup.execute({"action": "signin"})
    assert setup.verification_url is None
    assert not fake.shell


@pytest.mark.asyncio
async def test_approval_link_is_ephemeral_and_shell_requires_owner_approval():
    fake = FakePiConnect()
    now = [1.0]

    async def no_qr(_url):
        return None

    setup = PiConnectSetup(fake, no_qr, lambda: now[0], installed=lambda: True)
    with pytest.raises(ValueError, match="Approve this Pi"):
        await setup.execute({"action": "shell_on"})
    await setup.execute({"action": "signin"})
    now[0] = 602
    assert "verification_url" not in await setup.execute({"action": "status"})
    assert not fake.shell
    fake.signed_in = True  # the owner approved the device at Raspberry Pi Connect
    result = await setup.execute({"action": "shell_on"})
    assert result["remote_shell"] and fake.shell
    result = await setup.execute({"action": "shell_off"})
    assert not result["remote_shell"] and not fake.shell


@pytest.mark.asyncio
async def test_not_installed_fails_closed_without_starting_any_command():
    fake = FakePiConnect()
    setup = PiConnectSetup(fake, installed=lambda: False)
    assert await setup.execute({"action": "signin"}) == {
        "available": False, "state": "not_installed", "signed_in": False, "remote_shell": False}
    assert fake.calls == []


def test_pi_connect_api_is_local_only_strict_and_not_cacheable(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path)
    broker = AsyncMock(return_value={"available": True, "state": "off", "signed_in": False,
                                    "remote_shell": False})
    monkeypatch.setattr("luma.api.pi_connect_request", broker)
    local = TestClient(app)
    token = app.state.security.get_or_create_lan_token()
    remote = TestClient(app, client=("100.101.102.103", 5000))
    assert remote.post("/api/v1/pi-connect", json={"action": "status"},
                       headers={"X-Luma-Token": token}).status_code == 403
    assert local.post("/api/v1/pi-connect", json={"action": "status"},
                      headers={"Origin": "https://attacker.example"}).status_code == 403
    assert local.post("/api/v1/pi-connect", json={"action": "shell_on", "command": "sudo id"}).status_code == 422
    response = local.post("/api/v1/pi-connect", json={"action": "status"})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json()["state"] == "off"
    broker.assert_awaited_once_with({"action": "status"})


def test_image_installs_a_limited_lingering_admin_connect_broker():
    root = Path(__file__).resolve().parents[2]
    installer = (root / "system/install.sh").read_text()
    service = (root / "system/luma-pi-connect-setup.service").read_text()
    socket = (root / "system/luma-pi-connect-setup.socket").read_text()
    assert "rpi-connect qrencode" in installer
    assert "/var/lib/systemd/linger/luma-admin" in installer
    assert "luma-pi-connect-setup.socket" in installer
    assert "User=luma-admin" in service and "NoNewPrivileges=true" in service
    assert "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6" in service
    assert "SocketGroup=luma" in socket and "SocketMode=0660" in socket


@pytest.mark.asyncio
@pytest.mark.skipif(not hasattr(socket, "SO_PEERCRED"), reason="Linux Unix peer credentials required")
async def test_broker_accepts_luma_uid_and_denies_other_kernel_peer_uid(tmp_path, monkeypatch):
    async def launch(path, permitted_uid):
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(path))
        listener.listen()
        listener.setblocking(False)
        manager = PiConnectSetup(installed=lambda: False)
        task = asyncio.create_task(pi_connect_module.serve(
            listener=listener, owner_uid=permitted_uid, manager=manager))
        await asyncio.sleep(0)
        return task

    socket_path = tmp_path / "pi-connect.sock"
    monkeypatch.setattr(pi_connect_module, "SOCKET", str(socket_path))
    current_uid = os.getuid()
    server = await launch(socket_path, current_uid)
    try:
        status = await pi_connect_module.pi_connect_request({"action": "status"})
        assert status == {"available": False, "state": "not_installed",
                          "signed_in": False, "remote_shell": False}
    finally:
        server.cancel()
        with pytest.raises(asyncio.CancelledError):
            await server

    socket_path.unlink(missing_ok=True)
    denied_server = await launch(socket_path, current_uid + 1)
    try:
        reader, writer = await asyncio.open_unix_connection(str(socket_path))
        writer.write(b'{"action":"status"}\n')
        await writer.drain()
        try:
            response = await asyncio.wait_for(reader.readline(), 2)
        except ConnectionResetError:
            response = b""
        assert response == b""
        writer.close()
        try:
            await writer.wait_closed()
        except ConnectionResetError:
            pass
    finally:
        denied_server.cancel()
        with pytest.raises(asyncio.CancelledError):
            await denied_server
