from datetime import UTC, datetime, timedelta
import json
import queue
import struct

import httpx
import pytest
from fastapi.testclient import TestClient

from luma.api import create_app
from luma.models import CalendarEvent
from luma.voice import WakeGate, parse_local_command
from luma.voice_agent import (_arm_call_trial, _calibration_boundary_changed,
                              _discard_pending_audio, _reset_gapped_decoding,
                              _recover_preview_failure, _reset_voice_transition,
                              calibration_decoding_payload,
                              choose_command, partial_has_wake, select_command)
from luma.voice_audio import AudioCaptureError
from luma.voice_speech import VoicePlaybackError
from luma.voice_signal import AudioPreprocessor, AudioProfile, CalibrationSegmenter
from luma.voice_adaptation import PhraseAdaptations
from luma.voice_agent import accept_live_utterance
from luma.voice_wake import WakeAudioBuffer
from luma.voice_agent import present_voice_response


def test_unknown_command_is_silent_ephemeral_and_privacy_safe(tmp_path, monkeypatch):
    from unittest.mock import Mock
    import luma.service as service_module
    clock = [100.0]
    monkeypatch.setattr(service_module, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(service_module, 'randbelow', lambda bound: 0)
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    response = client.post('/api/v1/voice/command', json={
        'text': 'flibbertigibbet purple banana'}).json()
    assert response == {'accepted': False, 'message': 'Unknown command', 'speak': False}
    say, phase = Mock(), Mock()
    present_voice_response(response, say=say, phase=phase)
    say.assert_not_called()
    phase.assert_not_called()
    view = client.get('/api/v1/state').json()
    assert view['voice_notice'] == {'id': 1, 'remaining_ms': 3000}
    assert view['privacy_redacted']
    assert not view['notifications']
    assert not app.state.luma._pending_notification_chimes
    clock[0] += 3.1
    assert client.get('/api/v1/state').json()['voice_notice']['remaining_ms'] == 0
    assert create_app(data_dir=tmp_path).state.luma.snapshot()['voice_notice']['id'] == 0


def test_unknown_notice_id_does_not_repeat_after_api_restart(tmp_path, monkeypatch):
    import luma.service as service_module
    sequence = iter([42, 43])
    monkeypatch.setattr(service_module, 'randbelow', lambda bound: next(sequence))
    first = create_app(data_dir=tmp_path).state.luma
    first.unknown_voice_command()
    old_id = first.snapshot()['voice_notice']['id']
    restarted = create_app(data_dir=tmp_path).state.luma
    assert restarted.snapshot()['voice_notice']['id'] == 0
    restarted.unknown_voice_command()
    assert restarted.snapshot()['voice_notice']['id'] == old_id + 1
    assert 0 < old_id < 2**53  # exact JavaScript integer; no saved transcript


def test_valid_commands_keep_spoken_feedback_and_playback_failure_reporting():
    from unittest.mock import Mock
    say, phase = Mock(return_value='kristin'), Mock()
    present_voice_response({'accepted': True, 'message': 'It is noon.'}, say=say, phase=phase)
    say.assert_called_once_with('It is noon.')
    phase.assert_called_once_with('thinking')
    say.return_value = 'silent'
    phase.reset_mock()
    present_voice_response({'message': 'It is noon.'}, say=say, phase=phase)
    assert [call.args[0] for call in phase.call_args_list] == ['thinking', 'error']


def test_live_protected_wake_rejects_forced_conversation_before_opening_command_window():
    from unittest.mock import Mock
    independent = Mock()
    independent.AcceptWaveform.return_value = False
    independent.FinalResult.return_value = json.dumps({'text': 'we should move on to the next slide'})
    frames = WakeAudioBuffer()
    frames.append(bytes(8000))
    gate = WakeGate()
    accepted, heard, discard = accept_live_utterance('hey luma good morning', frames,
        independent, gate, 100, 'dual_decoder')
    assert discard and accepted is None and gate.until == 0
    assert heard == 'we should move on to the next slide'
    assert gate.accept('good morning', 101) is None


def test_live_verified_wake_allows_only_one_followup_and_incomplete_audio_revokes_it():
    from unittest.mock import Mock
    independent = Mock()
    independent.AcceptWaveform.return_value = False
    independent.FinalResult.return_value = json.dumps({'text': 'hey luma'})
    frames = WakeAudioBuffer()
    frames.append(bytes(8000))
    gate = WakeGate()
    assert accept_live_utterance('hey luma', frames, independent, gate, 100, 'dual_decoder') == (
        '', 'hey luma', False)
    accepted, _, discard = accept_live_utterance('what time is it', frames, independent, gate,
                                               101, 'dual_decoder')
    assert accepted == 'what time is it' and not discard and gate.until == 0
    assert accept_live_utterance('good morning', frames, independent, gate, 102, 'dual_decoder')[0] is None
    for _ in range(37):
        frames.append(bytes(8000))
    independent.Reset.reset_mock()
    gate.until = 110
    assert accept_live_utterance('hey luma good morning', frames, independent, gate,
                                103, 'dual_decoder') == (None, None, True)
    assert gate.until == 0
    independent.Reset.assert_not_called()


def test_calibration_decodes_tuned_audio_before_raw_comparison_or_intent():
    raw = struct.pack('<h', 1000) * 4000
    profile = AudioProfile(gain=2, quality='quiet')
    tuned = AudioPreprocessor(profile).process(raw)
    assert tuned != raw

    class Recorder:
        def __init__(self, transcript):
            self.transcript = transcript
            self.frames = []
            self.replays = []

        def Reset(self):
            self.frames = []

        def AcceptWaveform(self, frame):
            self.frames.append(frame)
            return False

        def FinalResult(self):
            self.replays.append(list(self.frames))
            return json.dumps({'text': self.transcript(self.frames[0])})

    constrained = Recorder(lambda _frame: 'hey luma what time is it')
    unrestricted = Recorder(lambda frame: (
        "hey luma what's the time" if frame == tuned else 'hey luma what time is it'))
    result = calibration_decoding_payload(
        constrained, unrestricted, [raw], [tuned], wake_phrase='hey luma',
        noise_rms=.001, profile=profile, now=100)
    assert constrained.replays == [[tuned], [raw]]
    assert unrestricted.replays == [[tuned], [raw]]
    assert result['selection'] == 'agree'
    assert result['selected_text'] == "what's the time"
    assert result['raw_compared'] and result['raw_free_text'] == 'hey luma what time is it'
    assert result['raw_constrained_wake'] is True
    assert result['rms'] > .02 and result['peak'] < .995

    untouched = Recorder(lambda _frame: 'hey luma what time is it')
    result = calibration_decoding_payload(
        constrained, untouched, [raw], [raw], wake_phrase='hey luma',
        noise_rms=.001, profile=AudioProfile(), now=101)
    assert untouched.replays == [[raw]]
    assert not result['raw_compared'] and result['raw_free_text'] == ''
    assert result['raw_constrained_wake'] is None

    learned = PhraseAdaptations()
    assert learned.add('whats the tea', 'what time is it')
    result = calibration_decoding_payload(
        Recorder(lambda _frame: 'hey luma good morning'),
        Recorder(lambda _frame: 'hey luma whats the tea'),
        [raw], [raw], wake_phrase='hey luma', noise_rms=.001,
        profile=AudioProfile(), now=102, adaptations=learned)
    assert result['selected_text'] is None
    assert result['selection'] == 'conflict'


def test_calibration_discards_stale_capture_without_hiding_terminal_failure():
    chunks = queue.Queue(maxsize=4)
    chunks.put(b'old speech')
    chunks.put(b'old tail')
    failure = AudioCaptureError('capture_stream_stopped')
    chunks.put(failure)
    _discard_pending_audio(chunks)
    assert chunks.get_nowait() is failure
    assert chunks.empty()


def test_speaker_route_failure_keeps_warm_voice_worker():
    class Worker:
        def __init__(self):
            self.closes = 0

        def close(self):
            self.closes += 1

    worker = Worker()
    _recover_preview_failure(worker, VoicePlaybackError('speaker_route_unavailable'))
    _recover_preview_failure(worker, VoicePlaybackError('audio_session_unavailable'))
    assert worker.closes == 0
    _recover_preview_failure(worker, VoicePlaybackError('piper_model_load_failed'))
    assert worker.closes == 1


def test_late_capture_gap_resets_both_decoders_wake_and_audio_state():
    class Recorder:
        def __init__(self):
            self.resets = 0
        def Reset(self):
            self.resets += 1

    chunks = queue.Queue(maxsize=4)
    chunks.put(b'old audio')
    failure = AudioCaptureError('capture_stream_stopped')
    chunks.put(failure)
    constrained, unrestricted = Recorder(), Recorder()
    processor = AudioPreprocessor(AudioProfile(gain=2, quality='quiet'))
    processor.applied_gain = .5
    gate = WakeGate()
    gate.until = 100
    _reset_gapped_decoding(chunks, constrained, unrestricted, processor, gate)
    assert constrained.resets == unrestricted.resets == 1
    assert processor.applied_gain == 2
    assert gate.until == 0
    assert chunks.get_nowait() is failure and chunks.empty()


def test_voice_session_boundary_discards_both_decoder_histories_and_old_audio():
    class Recorder:
        def __init__(self):
            self.resets = 0
        def Reset(self):
            self.resets += 1

    chunks = queue.Queue(maxsize=4)
    chunks.put(b'captured before the new check')
    failure = AudioCaptureError('capture_stream_stopped')
    chunks.put(failure)
    constrained, unrestricted = Recorder(), Recorder()
    processor = AudioPreprocessor(AudioProfile(gain=2, quality='quiet'))
    processor.applied_gain = .5
    gate = WakeGate()
    gate.until = 100
    segmenter = CalibrationSegmenter()
    segmenter.preroll.append((b'old raw', b'old tuned'))
    segmenter.loud_frames = 1
    utterance, raw_utterance = [b'old tuned'], [b'old raw']
    _reset_voice_transition(chunks, constrained, unrestricted, processor, gate,
                            segmenter, utterance, raw_utterance)
    assert constrained.resets == unrestricted.resets == 1
    assert processor.applied_gain == 2 and gate.until == 0
    assert not utterance and not raw_utterance
    assert not segmenter.preroll and segmenter.loud_frames == 0
    assert chunks.get_nowait() is failure and chunks.empty()


def test_agent_accepts_only_matching_armed_call_trial_acknowledgment():
    session = 'a' * 32
    def handler(request):
        assert request.url.path == '/api/v1/voice/call-trial/armed'
        assert json.loads(request.content) == {'session': session}
        return httpx.Response(200, json={
            'session': session, 'active': True, 'armed': True,
        })
    with httpx.Client(transport=httpx.MockTransport(handler), base_url='http://127.0.0.1') as client:
        assert _arm_call_trial(client, {'session': session})['armed']
    def wrong_session(_request):
        return httpx.Response(200, json={
            'session': 'b' * 32, 'active': True, 'armed': True,
        })
    with httpx.Client(transport=httpx.MockTransport(wrong_session), base_url='http://127.0.0.1') as client:
        with pytest.raises(ValueError, match='not armed'):
            _arm_call_trial(client, {'session': session})


def test_gain_restart_is_a_new_voice_boundary_with_the_same_session():
    before = {'active': True, 'session': 'same-session', 'capture_revision': 3}
    assert not _calibration_boundary_changed(before, dict(before))
    assert _calibration_boundary_changed(before, {**before, 'capture_revision': 4})
    assert _calibration_boundary_changed(before, {**before, 'active': False})


def test_wake_gate_requires_phrase_and_expires():
    gate = WakeGate()
    assert gate.accept("good night", 100) is None
    assert gate.accept("hey luma", 100) == ""
    assert gate.accept("brightness fifty", 103) == "brightness fifty"
    assert gate.accept("good night", 104) is None
    assert gate.accept("hey luma good morning", 110) == "good morning"
    assert gate.accept("hey luma", 120) == ""
    assert gate.accept("good night", 128) is None


def test_partial_wake_can_animate_before_final_but_cannot_authorize_action():
    assert partial_has_wake('{"partial":"hey luma what"}', "hey luma")
    assert partial_has_wake('{"partial":"[unk] hey   luma"}', "hey luma")
    assert not partial_has_wake('{"partial":"hey luna what"}', "hey luma")
    assert not partial_has_wake('{"partial":"hey luminary"}', "hey luma")
    assert not partial_has_wake('{"text":"hey luma"}', "hey luma")
    assert not partial_has_wake('{bad json', "hey luma")


def test_dual_decoder_keeps_known_command_when_free_dictation_is_bad():
    assert choose_command("good morning", "hey luma blue marlin", "hey luma") == (
        "good morning", "constrained")
    assert choose_command("what time is it", "hey luma blue marlin", "hey luma") == (
        "what time is it", "constrained")
    assert choose_command("", "hey luma what's the time", "hey luma") == (
        "what's the time", "free")


def test_dual_decoder_allows_a_title_only_when_timer_durations_agree():
    assert choose_command('',
                          'hey luma start a timer for seven seconds titled stretch', 'hey luma') == (
        None, 'timer_duration_unconfirmed')
    assert choose_command('unrecognized phrase',
                          'hey luma start a timer for seven seconds titled stretch', 'hey luma') == (
        None, 'timer_duration_unconfirmed')
    assert choose_command('start a seven second timer',
                          'hey luma start a timer for seven seconds titled stretch', 'hey luma') == (
        'start a timer for seven seconds titled stretch', 'free_title')
    assert choose_command('start a thirty second timer',
                          'hey luma start a thirty second timer titled tea', 'hey luma') == (
        'start a thirty second timer titled tea', 'free_title')
    assert choose_command('start a thirty minute timer',
                          'hey luma start a timer for thirty minutes called laundry', 'hey luma') == (
        'start a timer for thirty minutes called laundry', 'free_title')
    assert choose_command('start a thirty minute timer',
                          'hey luma start a timer for forty minutes called laundry', 'hey luma') == (
        None, 'conflict')
    assert choose_command('start a thirty minute timer',
                          'hey luma start a timer for thirty minutes called', 'hey luma') == (
        None, 'timer_name_unheard')


def test_dual_decoder_never_guesses_conflicting_actions_or_negations():
    assert choose_command("set brightness to fifty", "hey luma set brightness to sixty", "hey luma") == (
        None, "conflict")
    assert choose_command("good morning", "hey luma good night", "hey luma") == (None, "conflict")
    assert choose_command("set brightness to fifty", "hey luma do not set brightness to fifty", "hey luma") == (
        None, "negated")
    assert choose_command("what is the weather today", "hey luma what's the weather tomorrow", "hey luma") == (
        None, "conflict")
    assert choose_command("what is the weather today", "hey luma what's the forecast today", "hey luma") == (
        "what's the forecast today", "agree")
    assert choose_command("what time is it", "hey luma what's the date", "hey luma") == (
        None, "conflict")


def test_live_phrase_learning_resolves_only_a_confirmed_nonnegated_post_wake_phrase():
    learned = PhraseAdaptations()
    assert learned.add('whats the tea', 'what time is it')
    assert select_command('good morning', 'hey luma whats the tea', 'hey luma', learned) == (
        None, 'conflict')
    assert select_command('what time is it', 'hey luma whats the tea', 'hey luma', learned) == (
        'what time is it', 'learned')
    assert select_command('unrecognized phrase', 'hey luma whats the tea', 'hey luma', learned) == (
        'what time is it', 'learned')
    assert select_command('good morning', 'hey luma do not whats the tea', 'hey luma', learned) == (
        None, 'negated')
    assert select_command('good morning', 'whats the tea', 'hey luma', learned) == (
        'good morning', 'constrained')


def test_one_hundred_is_not_parsed_as_zero():
    assert parse_local_command("brightness one hundred").value == 100


def test_mute_cancels_calibration_and_rejects_late_voice_actions(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
    client.post('/api/v1/voice/wake-confirmation',json={'mode':'dual_decoder'})
    assert client.get("/api/v1/settings").json()["voice_enabled"] is True
    session = client.post("/api/v1/voice/calibration/start").json()["session"]
    client.post("/api/v1/voice/phase", json={"phase": "listening"})
    assert client.patch("/api/v1/settings", json={"voice_enabled": False}).status_code == 200
    assert not client.get("/api/v1/voice/calibration").json()["active"]
    assert client.post("/api/v1/voice/calibration/sample", json={
        "session": session, "text": "hey luma brightness fifty", "rms": .1, "peak": .6,
    }).status_code == 409
    assert not client.post("/api/v1/voice/command", json={"text": "brightness zero"}).json()["accepted"]
    assert not client.post("/api/v1/voice/phase", json={"phase": "speaking"}).json()["accepted"]
    state = client.get("/api/v1/state").json()
    assert state["settings"]["brightness"] == 70
    assert state["state"]["assistant_phase"] == "idle"
    assert client.patch("/api/v1/settings", json={"voice_enabled": True}).status_code == 200
    assert client.post("/api/v1/voice/command", json={"text": "brightness fifty"}).json()["accepted"]


def test_voice_morning_never_discloses_private_calendar(tmp_path):
    from synthetic_presence import authorize_primary
    app = create_app(data_dir=tmp_path)
    now = datetime.now(UTC)
    app.state.luma.update_settings({"visible_calendar_ids": ["primary"]})
    app.state.luma.replace_events([CalendarEvent("1", "primary", "Secret meeting", now, now + timedelta(hours=1))])
    client = TestClient(app)
    reply = client.post("/api/v1/voice/command", json={"text": "good morning"}).json()["message"]
    assert "Secret meeting" not in reply
    assert "private" in reply
    authorize_primary(app.state.luma)
    reply = client.post("/api/v1/voice/command", json={"text": "good morning"}).json()["message"]
    assert "Secret meeting" in reply
