import signal
import subprocess
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from luma.api import create_app
from luma.system_keyboard import SystemKeyboard, PALETTES


def keyboard_fixture():
    launch = Mock()
    launch.return_value.poll.return_value = None
    clock = Mock(return_value=100)
    return SystemKeyboard(launch, clock), launch, clock


def test_keyboard_is_explicit_fixed_command_and_never_logs_or_accepts_text():
    for theme in PALETTES:
        keyboard, launch, _ = keyboard_fixture()
        keyboard.apply({"id": None}, theme, True)
        launch.assert_not_called()
        keyboard.apply({"id": "one", "visible": True}, theme, True)
        args = launch.call_args.args[0]
        assert args[0] == "/opt/luma/bin/luma-keyboard"
        assert not {"-o", "-O", "-D", "--auto"}.intersection(args)
        assert launch.call_args.kwargs == {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        assert args[args.index("-R") + 1] == ("0" if theme == "neon-grid" else "8")
        assert keyboard.status() == "ok"


def test_repeated_poll_does_not_show_a_hidden_keyboard_or_extend_lease():
    keyboard, launch, clock = keyboard_fixture()
    request = {"id": "one", "visible": True}
    keyboard.apply(request, "hearth", True)
    clock.return_value = 999
    keyboard.apply(request, "hearth", True)
    launch.assert_called_once()
    launch.return_value.send_signal.assert_not_called()
    assert keyboard.deadline == 1000
    clock.return_value = 1000
    keyboard.apply(request, "hearth", True)
    launch.return_value.terminate.assert_called_once()
    assert keyboard.process is None
    keyboard.apply(request, "hearth", True)
    launch.assert_called_once()


def test_new_show_reveals_and_extends_but_sleep_consumes_stale_requests():
    keyboard, launch, clock = keyboard_fixture()
    keyboard.apply({"id": "one", "visible": True}, "hearth", True)
    clock.return_value = 200
    keyboard.apply({"id": "two", "visible": True}, "hearth", True)
    # Windows has no SIGUSR2; patch the platform symbol in this test there.
    launch.return_value.send_signal.assert_called_once_with(signal.SIGUSR2)
    assert keyboard.deadline == 1100
    keyboard.apply({"id": "three", "visible": True}, "hearth", False)
    assert keyboard.process is None
    keyboard.apply({"id": "three", "visible": True}, "hearth", True)
    launch.assert_called_once()


@pytest.fixture(autouse=True)
def linux_signal(monkeypatch):
    monkeypatch.setattr(signal, "SIGUSR2", getattr(signal, "SIGUSR2", 12), raising=False)


def test_close_and_expiry_terminate_only_owned_process():
    keyboard, launch, clock = keyboard_fixture()
    keyboard.apply({"id": "one", "visible": True}, "luma-glass", True)
    launch.return_value.wait.side_effect = [subprocess.TimeoutExpired("wvkbd", 1), 0]
    keyboard.apply({"id": "two", "visible": False}, "luma-glass", True)
    launch.return_value.kill.assert_called_once()
    assert keyboard.process is None
    keyboard.apply({"id": "three", "visible": True}, "luma-glass", True)
    launch.return_value.wait.side_effect = None
    clock.return_value = 1001
    keyboard.tick()  # Works even without a new API response.
    assert keyboard.process is None


def test_failed_launch_does_not_retry_every_poll_and_new_request_can_recover():
    keyboard, launch, _ = keyboard_fixture()
    launch.side_effect = FileNotFoundError()
    request = {"id": "one", "visible": True}
    with pytest.raises(OSError):
        keyboard.apply(request, "invalid;theme", True)
    keyboard.apply(request, "invalid;theme", True)
    launch.assert_called_once()
    assert keyboard.status() == "unavailable; retrying"
    launch.side_effect = None
    keyboard.apply({"id": "two", "visible": True}, "hearth", True)
    assert keyboard.status() == "ok"


def test_keyboard_requests_require_live_desktop_are_bounded_and_local(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    monkeypatch.setattr("luma.api.monotonic", lambda: 100)
    assert client.post("/api/v1/device/keyboard", json={"visible": True}).status_code == 503
    client.post("/api/v1/device/report", json={"controls": {}})
    assert client.post("/api/v1/device/keyboard", json={"visible": True}).status_code == 200
    first = client.get("/api/v1/device/keyboard-request").json()
    assert first["id"] and first["visible"]
    assert client.post("/api/v1/device/keyboard", json={"visible": True, "text": "not allowed"}).status_code == 422
    assert client.post("/api/v1/device/keyboard", json={"visible": "yes"}).status_code == 422
    assert client.post("/api/v1/device/keyboard", json={"visible": True}, headers={"Origin": "https://other.example"}).status_code == 403
    monkeypatch.setattr("luma.api.monotonic", lambda: 131)
    assert client.get("/api/v1/device/keyboard-request").json()["id"] is None
    client.post("/api/v1/commands", json={"name": "good_night"})
    assert client.post("/api/v1/device/keyboard", json={"visible": True}).status_code == 409
    assert client.post("/api/v1/device/keyboard", json={"visible": False}).status_code == 200
    lan = TestClient(app, client=("192.168.1.8", 1000))
    headers = {"X-Luma-Token": app.state.security.get_or_create_lan_token()}
    assert lan.post("/api/v1/device/keyboard", json={"visible": True}, headers=headers).status_code == 403
    assert lan.get("/api/v1/device/keyboard-request", headers=headers).status_code == 403
