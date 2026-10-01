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
    assert result["total"] == 10


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
        calibration.submit(session, PHRASES[0], .1, .5, 401)
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


def test_calibration_explains_when_live_audio_never_forms_a_phrase():
    calibration = VoiceCalibration()
    session = calibration.start(100, ambient_seconds=4)['session']
    calibration.report_level(session, .001, .01, 105, floor_rms=.001)
    assert 'Stay quiet' in calibration.status(106)['message']
    calibration.report_level(session, .001, .01, 121)
    quiet = calibration.status(121)
    assert quiet['attempts'] == 0 and quiet['completed'] == 0
    assert 'No speech has risen above' in quiet['message']
    calibration.report_level(session, .025, .25, 122)
    assert 'activity but no complete phrase' in calibration.status(122)['message']
    calibration.report_level(session, .08, .999, 123)
    assert 'clipping before a phrase completes' in calibration.status(123)['message']
    calibration.submit(session, '', .025, .25, 124)
    assert 'no complete phrase' not in calibration.status(124)['message']
    calibration.record_gain(43)
    assert 'Stay quiet' in calibration.status(125)['message']


def test_calibration_does_not_treat_missing_room_baseline_as_quiet_speech():
    calibration = VoiceCalibration()
    session = calibration.start(100, ambient_seconds=4)['session']
    calibration.report_level(session, .001, .01, 105)
    calibration.report_level(session, .001, .01, 121)
    status = calibration.status(121)
    assert 'Room sound was not measured' in status['message']
    assert status['room_noise_rms'] is None


def test_ambient_clock_begins_with_real_capture_and_profile_precedes_intents():
    calibration = VoiceCalibration()
    started = calibration.start(100, ambient_seconds=4)
    session = started['session']
    assert started['ambient_remaining'] == 4 and started['phrase'] is None
    assert calibration.submit(session, PHRASES[0], .025, .25, 102)['attempts'] == 0
    for now in (105, 106, 107, 108):
        calibration.report_level(session, .002, .02, now, floor_rms=.001)
    assert calibration.status(108)['ambient_remaining'] == 1
    assert calibration.submit(session, PHRASES[0], .025, .25, 108)['completed'] == 0
    for phrase in PHRASES:
        result = calibration.submit(session, phrase, .025, .25, 110)
    assert result['passed']
    assert result['audio_profile']['quality'] == 'quiet'
    assert result['audio_profile']['gain'] > 1
    assert 'text' not in json.dumps(result['audio_profile'])


def test_audio_candidate_is_derived_even_when_no_words_are_understood():
    calibration = VoiceCalibration()
    session = calibration.start(100)['session']
    for now in (101, 102, 103, 104):
        calibration.report_level(session, .001, .01, now, floor_rms=.001)
    for now in (105, 106, 107):
        status = calibration.submit(session, '', .025, .25, now)
    assert status['completed'] == 0 and status['attempts'] == 3
    assert status['audio_candidate']['gain'] > 1
    assert all(item['acoustic_speech'] and not item['matched'] for item in status['results'])


def test_raw_recognition_wins_twice_and_disables_harmful_trial():
    calibration = VoiceCalibration()
    session = calibration.start(100)['session']
    for now in (101, 102, 103, 104):
        calibration.report_level(session, .001, .01, now, floor_rms=.001)
    for now in (105, 106, 107):
        initial = calibration.submit(session, '', .025, .25, now)
    assert initial['audio_candidate']['gain'] > 1
    for now in (108, 109):
        outcome = calibration.submit(session, '', .025, .25, now,
                                     free_text='unrelated words',
                                     raw_free_text=PHRASES[0], raw_compared=True)
    assert outcome['processing_regressed']
    assert outcome['audio_candidate']['quality'] == 'bypass'
    assert outcome['audio_candidate']['gain'] == 1
    assert outcome['audio_candidate']['snr_db'] is not None
    assert 'Untouched audio' in outcome['message']
    assert outcome['last_raw_heard'] == PHRASES[0]
    assert all('raw_free_text' not in row for row in outcome['results'])
    for phrase in PHRASES:
        finished = calibration.submit(session, phrase, .025, .25, 110)
    assert finished['passed']
    assert finished['audio_profile']['quality'] == 'bypass'


def test_calibration_shows_raw_decoder_evidence_and_never_passes_a_conflict():
    calibration = VoiceCalibration()
    session = calibration.start(100)["session"]
    conflicted = calibration.submit(
        session, PHRASES[0], .05, .4, 101,
        free_text="hey luma set brightness to sixty", selected_text=None,
        selection="conflict",
    )
    assert conflicted["completed"] == 0
    assert conflicted["last_heard"] == "hey luma set brightness to sixty"
    assert conflicted["last_free_available"] is True
    assert conflicted["last_constrained"] == PHRASES[0]
    assert conflicted["last_wake_detected"] is True
    assert conflicted["last_intent"] == ""
    assert "disagreed" in conflicted["message"]
    selected = calibration.submit(
        session, "hey luma what time is it", .05, .4, 102,
        free_text="hey luma set brightness to fifty",
        selected_text="set brightness to fifty", selection="free",
    )
    assert selected["completed"] == 1
    assert selected["last_heard"] == "hey luma set brightness to fifty"
    assert selected["last_intent"] == "set_brightness: 50"
    assert calibration.status(118)["last_heard"] == ""
    assert calibration.status(118)["last_constrained"] == ""
    assert calibration.status(118)["last_selection"] == ""


def test_unrestricted_decoder_reveals_a_wake_missed_by_the_gate():
    calibration = VoiceCalibration()
    session = calibration.start(100)["session"]
    result = calibration.submit(
        session, "", .05, .4, 101,
        free_text="hey luma set brightness to fifty",
        selected_text=None, selection="",
    )
    assert result["completed"] == 0
    assert result["last_heard"] == "hey luma set brightness to fifty"
    assert result["last_free_available"] is True
    assert result["last_wake_detected"] is False
    assert "not Hey Luma" in result["message"]


def test_negative_control_requires_ordinary_speech_without_a_wake():
    calibration = VoiceCalibration()
    session = calibration.start(100)["session"]
    for phrase in PHRASES[:-2]:
        calibration.submit(session, phrase, .05, .4, 101)
    assert calibration.status(101)["expects_wake"] is False
    false_wake = calibration.submit(session, "hey luma what time is it", .05, .4, 102)
    assert false_wake["completed"] == len(PHRASES) - 2
    assert "False wake" in false_wake["message"]
    assert false_wake["last_expected_wake"] is False
    assert false_wake["last_wake_detected"] is True
    ordinary = calibration.submit(session, "what time is it", .05, .4, 103)
    assert ordinary["completed"] == len(PHRASES) - 1
    assert ordinary["last_wake_detected"] is False
    assert ordinary["last_expected_wake"] is False
    completed = calibration.submit(session, "", .05, .4, 104,
                                   free_text="good morning", selected_text=None)
    assert completed["passed"] is True


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


def test_hardware_gain_change_restarts_room_baseline_and_discards_old_acoustics():
    calibration = VoiceCalibration()
    session = calibration.start(100, ambient_seconds=4)['session']
    for now in (101, 102, 103, 104, 105):
        calibration.report_level(session, .001, .01, now, floor_rms=.001)
    assert calibration.submit(session, PHRASES[0], .025, .25, 106)['completed'] == 1
    assert calibration.room_floors and calibration.results
    calibration.record_gain(43)
    restarted = calibration.status(107)
    assert restarted['completed'] == restarted['attempts'] == 0
    assert restarted['ambient_remaining'] == 4
    assert restarted['audio_candidate'] is None
    assert restarted['room_noise_rms'] is None
    assert restarted['gain_adjustments'] == 1
    assert restarted['last_heard'] == ''
    assert calibration.submit(session, PHRASES[0], .025, .25, 107)['attempts'] == 0


def test_hardware_gain_does_not_amplify_a_low_signal_to_noise_room():
    calibration = VoiceCalibration()
    session = calibration.start(100)['session']
    for now in (101, 102, 103):
        calibration.report_level(session, .009, .08, now, floor_rms=.008)
    assert calibration.gain_step(.001, .05) == 0


def test_auto_gain_only_for_clear_level_faults(monkeypatch, tmp_path):
    import luma.api as api
    original_start = api.VoiceCalibration.start
    monkeypatch.setattr(api.VoiceCalibration, 'start',
                        lambda self, *args, **_kwargs: original_start(self, *args))
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


def test_calibration_api_suppresses_actions_and_lan_cannot_enable_microphone(tmp_path, monkeypatch):
    import luma.api as api
    original_start = api.VoiceCalibration.start
    monkeypatch.setattr(api.VoiceCalibration, 'start',
                        lambda self, *args, **_kwargs: original_start(self, *args))
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


def test_api_ambient_measurement_precedes_phrase_checks(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        started = client.post('/api/v1/voice/calibration/start').json()
        assert started['ambient_remaining'] >= 3
        assert started['phrase'] is None
        ignored = client.post('/api/v1/voice/calibration/sample', json={
            'session': started['session'], 'text': PHRASES[0], 'rms': .08, 'peak': .4,
        }).json()
        assert ignored['completed'] == 0 and ignored['attempts'] == 0
        assert ignored['applied_gain'] is None


def test_profile_persists_as_numeric_data_and_can_be_reset(tmp_path, monkeypatch):
    import luma.api as api
    original_start = api.VoiceCalibration.start
    monkeypatch.setattr(api.VoiceCalibration, 'start',
                        lambda self, *args, **_kwargs: original_start(self, *args))
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as client:
        session = client.post('/api/v1/voice/calibration/start').json()['session']
        for _ in range(4):
            client.post('/api/v1/voice/calibration/level', json={
                'session': session, 'rms': .001, 'peak': .01, 'floor_rms': .001,
            })
        for phrase in PHRASES:
            result = client.post('/api/v1/voice/calibration/sample', json={
                'session': session, 'text': phrase, 'rms': .025, 'peak': .25,
            })
        assert result.json()['passed']
        saved = app.state.luma.storage.get_cache('voice', 'audio_profile')
        assert saved['gain'] > 1 and saved['quality'] == 'quiet'
        assert 'hey luma' not in json.dumps(saved)
        assert client.get('/api/v1/voice/calibration').json()['audio_profile'] == saved
        reset = client.post('/api/v1/voice/audio-profile/reset').json()['audio_profile']
        assert reset['gain'] == 1 and reset['high_pass'] is False
        assert client.get('/api/v1/voice/calibration').json()['audio_profile'] == reset
        remote = TestClient(app, client=('192.168.1.7', 5000))
        assert remote.post('/api/v1/voice/audio-profile/reset').status_code == 403


def test_api_exposes_trial_audio_profile_before_intent_recognition_succeeds(tmp_path, monkeypatch):
    import luma.api as api
    original_start = api.VoiceCalibration.start
    monkeypatch.setattr(api.VoiceCalibration, 'start',
                        lambda self, *args, **_kwargs: original_start(self, *args))
    with TestClient(create_app(data_dir=tmp_path)) as client:
        session = client.post('/api/v1/voice/calibration/start').json()['session']
        for _ in range(4):
            client.post('/api/v1/voice/calibration/level', json={
                'session': session, 'rms': .001, 'peak': .01, 'floor_rms': .001,
            })
        for _ in range(3):
            result = client.post('/api/v1/voice/calibration/sample', json={
                'session': session, 'text': '', 'rms': .025, 'peak': .25,
            }).json()
        assert result['completed'] == 0
        assert result['audio_profile']['gain'] > 1
        assert result['audio_candidate']['gain'] == result['audio_profile']['gain']


def test_new_check_starts_untouched_and_restores_saved_profile_on_cancel(tmp_path, monkeypatch):
    import luma.api as api
    original_start = api.VoiceCalibration.start
    monkeypatch.setattr(api.VoiceCalibration, 'start',
                        lambda self, *args, **_kwargs: original_start(self, *args))
    app = create_app(data_dir=tmp_path)
    saved = {'version': 1, 'gain': 1.75, 'high_pass': False,
             'noise_rms': .001, 'speech_rms': .025, 'snr_db': 28.0,
             'quality': 'quiet'}
    app.state.luma.storage.set_cache('voice', 'audio_profile', saved)
    with TestClient(app) as client:
        assert client.get('/api/v1/voice/calibration').json()['audio_profile'] == saved
        started = client.post('/api/v1/voice/calibration/start').json()
        assert started['active'] and started['audio_profile']['gain'] == 1
        assert app.state.luma.storage.get_cache('voice', 'audio_profile') == saved
        cancelled = client.post('/api/v1/voice/calibration/cancel').json()
        assert not cancelled['active'] and cancelled['audio_profile'] == saved


def test_manual_mic_gain_change_restarts_active_room_measurement(tmp_path, monkeypatch):
    import luma.api as api
    gain = {'value': 39}
    def hardware_status():
        return {'available': True, 'gain': gain['value'], 'max_gain': 63,
                'capture_on': True, 'route_ready': True}
    def save_gain(value):
        gain['value'] = value
        return hardware_status()
    monkeypatch.setattr(api.mic_hardware, 'status', hardware_status)
    monkeypatch.setattr(api.mic_hardware, 'save_and_apply', save_gain)
    with TestClient(create_app(data_dir=tmp_path)) as client:
        session = client.post('/api/v1/voice/calibration/start').json()['session']
        for _ in range(4):
            client.post('/api/v1/voice/calibration/level', json={
                'session': session, 'rms': .001, 'peak': .01, 'floor_rms': .001,
            })
        assert client.get('/api/v1/voice/calibration').json()['room_noise_rms'] == .001
        changed = client.post('/api/v1/voice/hardware/gain', json={'gain': 45})
        assert changed.status_code == 200 and changed.json()['gain'] == 45
        status = client.get('/api/v1/voice/calibration').json()
        assert status['active'] and status['completed'] == 0
        assert status['ambient_remaining'] == 4
        assert status['room_noise_rms'] is None
        assert status['applied_gain'] == 45
        unchanged = client.post('/api/v1/voice/hardware/gain', json={'gain': 45})
        assert unchanged.status_code == 200
        assert client.get('/api/v1/voice/calibration').json()['gain_adjustments'] == 1


def test_owner_can_save_clean_audio_tuning_before_any_phrase_matches(tmp_path, monkeypatch):
    import luma.api as api
    original_start = api.VoiceCalibration.start
    monkeypatch.setattr(api.VoiceCalibration, 'start',
                        lambda self, *args, **_kwargs: original_start(self, *args))
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as client:
        session = client.post('/api/v1/voice/calibration/start').json()['session']
        assert client.post('/api/v1/voice/calibration/save-audio', json={
            'session': session,
        }).status_code == 409
        for _ in range(4):
            client.post('/api/v1/voice/calibration/level', json={
                'session': session, 'rms': .001, 'peak': .01, 'floor_rms': .001,
            })
        for _ in range(3):
            client.post('/api/v1/voice/calibration/sample', json={
                'session': session, 'text': '', 'rms': .025, 'peak': .25,
            })
        assert client.post('/api/v1/voice/calibration/save-audio', json={
            'session': '0' * 32,
        }).status_code == 409
        remote = TestClient(app, client=('192.168.1.7', 5000))
        assert remote.post('/api/v1/voice/calibration/save-audio', json={
            'session': session,
        }).status_code == 403
        saved = client.post('/api/v1/voice/calibration/save-audio', json={
            'session': session,
        })
        assert saved.status_code == 200
        assert not saved.json()['active']
        profile = app.state.luma.storage.get_cache('voice', 'audio_profile')
        assert profile['gain'] > 1 and profile['quality'] == 'quiet'
        assert 'hey luma' not in json.dumps(profile)


def test_regressed_audio_trial_cannot_be_saved(tmp_path, monkeypatch):
    import luma.api as api
    original_start = api.VoiceCalibration.start
    monkeypatch.setattr(api.VoiceCalibration, 'start',
                        lambda self, *args, **_kwargs: original_start(self, *args))
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as client:
        session = client.post('/api/v1/voice/calibration/start').json()['session']
        for _ in range(4):
            client.post('/api/v1/voice/calibration/level', json={
                'session': session, 'rms': .001, 'peak': .01, 'floor_rms': .001,
            })
        for _ in range(3):
            client.post('/api/v1/voice/calibration/sample', json={
                'session': session, 'text': '', 'rms': .025, 'peak': .25,
            })
        for _ in range(2):
            result = client.post('/api/v1/voice/calibration/sample', json={
                'session': session, 'text': '', 'free_text': 'unrelated',
                'raw_free_text': PHRASES[0], 'raw_compared': True,
                'rms': .025, 'peak': .25,
            })
        assert result.json()['processing_regressed']
        assert client.post('/api/v1/voice/calibration/save-audio', json={
            'session': session,
        }).status_code == 409
        assert app.state.luma.storage.get_cache('voice', 'audio_profile') is None


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
