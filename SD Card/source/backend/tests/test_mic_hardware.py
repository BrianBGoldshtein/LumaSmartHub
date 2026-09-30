from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from luma import mic_hardware
from luma.api import create_app


def test_capture_defaults_apply_only_relevant_fixed_mixer_controls(monkeypatch):
    calls = []

    def runner(*args):
        calls.append(args)
        return "  : values=39,39\n" if args == ("cget", "name=Capture Volume") else ""

    monkeypatch.setattr(mic_hardware, "_run", runner)
    mic_hardware.apply(39)
    assert calls[0] == ("cget", "name=Capture Volume")
    assert calls[-2:] == [("cset", "name=Capture Switch", "on,on"),
                         ("cset", "name=Capture Volume", "39,39")]
    assert all("Playback" not in str(call) for call in calls)


@pytest.mark.parametrize("gain", [-1, 64, True, 1.5, "39"])
def test_invalid_gain_never_reaches_hardware(monkeypatch, gain):
    monkeypatch.setattr(mic_hardware, "_run", lambda *args: pytest.fail("hardware touched"))
    with pytest.raises(ValueError):
        mic_hardware.apply(gain)


def test_gain_is_saved_for_reboot_and_status_shows_capture_path(tmp_path, monkeypatch):
    values = {"Capture Volume": "39,39", "Capture Switch": "on,on"}
    values.update({name: "on" for name in mic_hardware.ROUTE_ON})

    def runner(*args):
        name = args[1].removeprefix("name=")
        if args[0] == "cset":
            values[name] = args[2]
        return f"  : values={values[name]}\n"

    monkeypatch.setattr(mic_hardware, "_run", runner)
    path = tmp_path / "gain"
    result = mic_hardware.save_and_apply(43, path)
    assert result == {"available": True, "gain": 43, "max_gain": 63,
                      "capture_on": True, "route_ready": True}
    assert path.read_text() == "43\n" and mic_hardware.saved_gain(path) == 43
    assert mic_hardware.status(path)["gain"] == 43


def test_missing_card_fails_closed_and_does_not_save(tmp_path, monkeypatch):
    def missing(*_args):
        raise mic_hardware.MicHardwareError("missing")

    monkeypatch.setattr(mic_hardware, "_run", missing)
    path = tmp_path / "gain"
    assert not mic_hardware.status(path)["available"]
    with pytest.raises(mic_hardware.MicHardwareError):
        mic_hardware.save_and_apply(45, path)
    assert not path.exists()


def test_hardware_routes_are_local_only_and_strict(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path)
    monkeypatch.setattr(mic_hardware, "status", lambda: {"available": False, "gain": 39,
                       "max_gain": 63, "capture_on": False, "route_ready": False})
    calls = []
    monkeypatch.setattr(mic_hardware, "save_and_apply", lambda gain: calls.append(gain) or
                        {"available": True, "gain": gain, "max_gain": 63,
                         "capture_on": True, "route_ready": True})
    local = TestClient(app)
    token = app.state.security.get_or_create_lan_token()
    remote = TestClient(app, client=("100.101.102.103", 5000))
    assert remote.get("/api/v1/voice/hardware", headers={"X-Luma-Token": token}).status_code == 403
    assert remote.post("/api/v1/voice/hardware/gain", json={"gain": 43},
                       headers={"X-Luma-Token": token}).status_code == 403
    assert local.get("/api/v1/voice/hardware").json()["available"] is False
    assert local.post("/api/v1/voice/hardware/gain", json={"gain": True}).status_code == 422
    assert local.post("/api/v1/voice/hardware/gain", json={"gain": 64}).status_code == 422
    assert local.post("/api/v1/voice/hardware/gain", json={"gain": 43, "extra": 1}).status_code == 422
    assert local.post("/api/v1/voice/hardware/gain", json={"gain": 43}).json()["gain"] == 43
    assert calls == [43]
