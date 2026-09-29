from unittest.mock import Mock

from fastapi.testclient import TestClient

from luma.api import create_app
from luma.device_agent import DeviceBridge
from luma.touch import is_touchscreen


def test_default_voice_starts_and_saved_mute_survives_restart(tmp_path):
    app = create_app(data_dir=tmp_path)
    voice = Mock()
    bridge = DeviceBridge(Mock(), Mock(), voice)
    bridge.apply(app.state.luma.snapshot(), 0)
    voice.set_enabled.assert_called_once_with(True)
    client = TestClient(app)
    assert client.patch("/api/v1/settings", json={"voice_enabled": False}).status_code == 200
    bridge.apply(app.state.luma.snapshot(), 2)
    voice.set_enabled.assert_called_with(False)
    restarted = create_app(data_dir=tmp_path)
    assert restarted.state.luma.settings.voice_enabled is False
    voice.reset_mock()
    DeviceBridge(Mock(), Mock(), voice).apply(restarted.state.luma.snapshot(), 0)
    voice.set_enabled.assert_called_once_with(False)


def test_missing_voice_setting_does_not_start_microphone():
    voice = Mock()
    snapshot = {"settings": {"orientation": "landscape", "brightness": 70, "volume": 55},
                "state": {"display_power": "on"}}
    DeviceBridge(Mock(), Mock(), voice).apply(snapshot, 0)
    voice.set_enabled.assert_called_once_with(False)


def test_mute_is_not_delayed_by_failed_voice_start_backoff(tmp_path):
    snapshot = create_app(data_dir=tmp_path).state.luma.snapshot()
    voice = Mock()
    voice.set_enabled.return_value = False
    bridge = DeviceBridge(Mock(), Mock(), voice)
    assert bridge.apply(snapshot, 0)["voice"] == "unavailable; retrying"
    bridge.apply(snapshot, 2)
    voice.set_enabled.assert_called_once_with(True)
    snapshot["settings"]["voice_enabled"] = False
    voice.set_enabled.return_value = True
    assert bridge.apply(snapshot, 3)["voice"] == "ok"
    voice.set_enabled.assert_called_with(False)
    assert "voice" not in bridge.retry_at
    # A subsequent explicit re-enable need not wait for the obsolete retry.
    snapshot["settings"]["voice_enabled"] = True
    bridge.apply(snapshot, 4)
    voice.set_enabled.assert_called_with(True)
    assert voice.set_enabled.call_count == 3


def test_touch_wake_excludes_keyboards_and_pointer_only_devices():
    assert is_touchscreen({3: [53, 54, 57]})
    assert is_touchscreen({1: [330], 3: [0, 1]})
    assert not is_touchscreen({1: [30, 31, 32]})
    assert not is_touchscreen({2: [0, 1]})


def test_bridge_applies_changes_once_and_retries_failures():
    display, audio = Mock(), Mock()
    display.set_brightness.return_value = False
    bridge = DeviceBridge(display, audio)
    state = {"settings": {"orientation": "landscape", "brightness": 70, "volume": 55}, "state": {"display_power": "on"}}
    assert bridge.apply(state, 0)["brightness"] == "unavailable; retrying"
    bridge.apply(state, 2)
    audio.set_volume.assert_called_once_with(55)
    display.power.assert_called_once_with(True)
    display.set_brightness.assert_called_once_with(70)
    display.set_brightness.return_value = True
    assert bridge.apply(state, 61)["brightness"] == "ok"
    state["state"]["display_power"] = "off"
    bridge.apply(state, 62)
    display.power.assert_called_with(False)


def test_local_device_report_and_cross_origin_rejection(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
    assert client.post("/api/v1/device/report", json={"controls": {"volume": "ok"}}).status_code == 200
    assert client.get("/api/v1/diagnostics").json()["hardware"]["controls"]["volume"] == "ok"
    assert client.post("/api/v1/commands", headers={"Origin": "https://evil.example"}, json={"name": "good_night"}).status_code == 403
    assert client.get("/api/v1/security/lan-token", headers={"Host": "evil.example"}).status_code == 403


def test_lan_token_cannot_forge_device_report(tmp_path):
    app = create_app(data_dir=tmp_path)
    token = app.state.security.get_or_create_lan_token()
    client = TestClient(app, client=("192.168.1.20", 50000))
    assert client.post("/api/v1/device/report", headers={"X-Luma-Token": token}, json={"controls": {}}).status_code == 403
