import json
import subprocess
from unittest.mock import Mock, call

import pytest
from fastapi.testclient import TestClient

from luma.api import create_app
from luma.hardware import AudioController, VoiceController
from luma.leds import status_frame
from luma.voice import command_grammar, parse_local_command
from luma.voice_calibration import PHRASES, VoiceCalibration


def test_calibration_passes_without_retaining_transcripts():
    calibration = VoiceCalibration()
    session = calibration.start(100)["session"]
    for phrase in PHRASES:
        result = calibration.submit(session, phrase, .08, .6, 101)
    assert result["passed"] and not result["active"]
    assert all("text" not in row for row in result["results"])
    assert result["completed"] == len(PHRASES)


def test_calibration_rejects_wrong_wake_quiet_clipped_and_expired_samples():
    calibration = VoiceCalibration()
    session = calibration.start(100)["session"]
    assert calibration.submit(session, "set brightness to fifty", .1, .5, 101)["completed"] == 0
    missing_wake = calibration.status(101)
    assert missing_wake["last_wake_detected"] is False
    assert missing_wake["last_intent"] == ""
    assert "not Hey Luma" in missing_wake["message"]
    wrong_command = calibration.submit(session, "hey luma good morning", .1, .5, 101)
    assert wrong_command["last_wake_detected"] is True
    assert wrong_command["last_intent"] == "good_morning"
    assert "different command" in wrong_command["message"]
    assert "quiet" in calibration.submit(session, PHRASES[0], .0001, .01, 101)["message"]
    assert "clipping" in calibration.submit(session, PHRASES[0], .1, .999, 101)["message"]
    with pytest.raises(ValueError):
        calibration.submit(session, PHRASES[0], .1, .5, 281)
    with pytest.raises(ValueError):
        calibration.submit("old-session", PHRASES[0], .1, .5, 101)


def test_calibration_level_is_live_ephemeral_and_expires():
    calibration = VoiceCalibration()
    session = calibration.start(100)["session"]
    live = calibration.report_level(session, .04, .3, 101)
    assert live["signal_available"] and live["signal_rms"] == .04 and live["signal_peak"] == .3
    assert not live["results"]
    assert not calibration.status(105)["signal_available"]
    assert calibration.status(117)["last_wake_detected"] is None
    assert calibration.status(117)["last_intent"] == ""
    with pytest.raises(ValueError):
        calibration.report_level("old-session", .1, .4, 102)


def test_gain_tuning_is_bounded_and_transcript_is_ephemeral():
    calibration = VoiceCalibration()
    session = calibration.start(100)["session"]
    result = calibration.submit(session, "hey luma something unclear", .001, .05, 101)
    assert result["last_heard"] == "hey luma something unclear"
    assert calibration.gain_step(.001, .05) == 4
    calibration.record_gain(43)
    assert calibration.status(102)["applied_gain"] == 43
    assert calibration.gain_step(.05, .999) == -4
    calibration.record_gain(39)
    calibration.record_gain(35)
    assert calibration.gain_step(.001, .05) == 0
    assert calibration.status(117)["last_heard"] == ""
    assert calibration.gain_step(.0001, .001) == 0  # absent route, not low gain
    calibration.cancel()
    assert calibration.status(102)["last_heard"] == ""


def test_auto_gain_only_for_clear_level_faults(monkeypatch, tmp_path):
    import luma.api as api
    applied = []
    monkeypatch.setattr(api.mic_hardware, 'status', lambda: {
        'available': True, 'gain': 39 + 4 * len(applied), 'max_gain': 63,
        'capture_on': True, 'route_ready': True,
    })
    monkeypatch.setattr(api.mic_hardware, 'save_and_apply', lambda gain: applied.append(gain))
    with TestClient(create_app(data_dir=tmp_path)) as client:
        session = client.post('/api/v1/voice/calibration/start').json()['session']
        response = client.post('/api/v1/voice/calibration/sample', json={
            'session': session, 'text': 'hey luma something unclear', 'rms': .001,
            'peak': .05,
        })
        assert response.status_code == 200
        assert response.json()['applied_gain'] == 43
        assert 'adjusted' in response.json()['message']
        assert applied == [43]
        client.post('/api/v1/voice/calibration/sample', json={
            'session': session, 'text': 'hey luma something unclear', 'rms': .05,
            'peak': .5,
        })
        assert applied == [43]  # Wrong transcript alone cannot change gain.


def test_calibration_api_suppresses_actions_and_lan_cannot_enable_microphone(tmp_path):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    assert client.patch("/api/v1/settings", json={"voice_enabled": False}).status_code == 200
    assert client.post("/api/v1/voice/calibration/start").status_code == 409
    assert client.patch("/api/v1/settings", json={"voice_enabled": True}).status_code == 200
    before = app.state.luma.settings.brightness
    started = client.post("/api/v1/voice/calibration/start").json()
    session = started["session"]
    assert not started["agent_available"]
    failed_start = client.post("/api/v1/voice/diagnostic", json={"code": "capture_source_unavailable"})
    assert failed_start.json()["accepted"]
    health = client.get("/api/v1/voice/calibration").json()
    assert not health["agent_available"] and health["agent_error"] == "capture_source_unavailable"
    assert client.post("/api/v1/voice/phase", json={"phase": "listening"}).json()["accepted"]
    health = client.get("/api/v1/voice/calibration").json()
    assert health["agent_available"] and health["agent_phase"] == "listening" and health["agent_error"] is None
    assert client.post("/api/v1/voice/heartbeat", json={"dropped_frames": 3}).status_code == 200
    assert client.get("/api/v1/voice/calibration").json()["dropped_frames"] == 3
    assert client.post("/api/v1/voice/heartbeat", json={"dropped_frames": -1}).status_code == 422
    level = client.post("/api/v1/voice/calibration/level", json={"session": session, "rms": .04, "peak": .3}).json()
    assert level["signal_available"] and level["signal_rms"] == .04
    assert not client.post("/api/v1/voice/command", json={"text": "brightness zero"}).json()["accepted"]
    for phrase in PHRASES:
        result = client.post("/api/v1/voice/calibration/sample", json={"session": session, "text": phrase, "rms": .1, "peak": .6})
        assert result.status_code == 200
    assert result.json()["passed"]
    assert app.state.luma.settings.brightness == before
    saved = app.state.luma.storage.get_cache("voice", "calibration")
    assert "hey luma" not in json.dumps(saved)
    remote = TestClient(app, client=("192.168.1.7", 5000))
    headers = {"X-Luma-Token": app.state.security.get_or_create_lan_token()}
    assert remote.patch("/api/v1/settings", json={"voice_enabled": True}, headers=headers).status_code == 403
    assert remote.get("/api/v1/voice/calibration", headers=headers).status_code == 403
    assert remote.post("/api/v1/voice/calibration/level", json={"session": session, "rms": .1, "peak": .5}, headers=headers).status_code == 403
    assert remote.post("/api/v1/voice/diagnostic", json={"code": "capture_source_unavailable"}, headers=headers).status_code == 403
    assert client.post("/api/v1/voice/diagnostic", json={"code": "arbitrary text"}).status_code == 422


def test_command_grammar_covers_supported_controls_and_unknown_audio():
    grammar = command_grammar()
    assert "[unk]" in grammar and "hey luma" in grammar
    for phrase in grammar:
        if phrase not in {"[unk]", "hey luma"}:
            assert parse_local_command(phrase) is not None


def test_voice_controller_attempts_service_start_even_if_model_is_missing():
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, "active\n"))
    controller = VoiceController(runner)
    assert controller.set_enabled(True)
    assert controller.set_enabled(False)
    assert runner.call_args_list == [
        call(["systemctl", "--user", "start", "luma-voice.service"]),
        call(["systemctl", "--user", "is-active", "luma-voice.service"]),
        call(["systemctl", "--user", "stop", "luma-voice.service"]),
    ]


def test_led_frames_are_bounded_and_idle_is_dark():
    for phase in ["listening", "thinking", "speaking", "error", "idle"]:
        frame = status_frame(phase)
        assert len(frame) == 20 and all(0 <= value <= 255 for value in frame)
        assert frame[:4] == [0] * 4 and frame[-4:] == [255] * 4
    assert status_frame("idle")[4:16] == [0xE2, 0, 0, 0] * 3


def test_audio_output_never_guesses_between_multiple_sinks():
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps([{"name": "hdmi-0"}, {"name": "hdmi-1"}])))
    audio = AudioController(runner)
    assert not audio.set_output("hdmi")
    assert runner.call_count == 1
    runner.return_value.stdout = json.dumps([{"name": "alsa_output.seeed2micvoicec", "properties": {}}])
    assert audio.set_output("hat")
    runner.assert_called_with(["pactl", "set-default-sink", "alsa_output.seeed2micvoicec"])
