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
from luma.voice_agent import (_arm_call_trial, _discard_pending_audio, _reset_gapped_decoding,
                              _reset_voice_transition,
                              calibration_decoding_payload,
                              choose_command, partial_has_wake, select_command)
from luma.voice_audio import AudioCaptureError
from luma.voice_signal import AudioPreprocessor, AudioProfile, CalibrationSegmenter
from luma.voice_adaptation import PhraseAdaptations


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
    assert result['selected_text'] == 'what time is it'
    assert result['selection'] == 'learned'


def test_calibration_discards_stale_capture_without_hiding_terminal_failure():
    chunks = queue.Queue(maxsize=4)
    chunks.put(b'old speech')
    chunks.put(b'old tail')
    failure = AudioCaptureError('capture_stream_stopped')
    chunks.put(failure)
    _discard_pending_audio(chunks)
    assert chunks.get_nowait() is failure
    assert chunks.empty()


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
        'what time is it', 'learned')
    assert select_command('good morning', 'hey luma do not whats the tea', 'hey luma', learned) == (
        None, 'negated')
    assert select_command('good morning', 'whats the tea', 'hey luma', learned) == (
        'good morning', 'constrained')


def test_one_hundred_is_not_parsed_as_zero():
    assert parse_local_command("brightness one hundred").value == 100


def test_mute_cancels_calibration_and_rejects_late_voice_actions(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
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
    app = create_app(data_dir=tmp_path)
    now = datetime.now(UTC)
    app.state.luma.update_settings({"visible_calendar_ids": ["primary"]})
    app.state.luma.replace_events([CalendarEvent("1", "primary", "Secret meeting", now, now + timedelta(hours=1))])
    client = TestClient(app)
    reply = client.post("/api/v1/voice/command", json={"text": "good morning"}).json()["message"]
    assert "Secret meeting" not in reply
    assert "private" in reply
    app.state.luma.phone_seen()
    reply = client.post("/api/v1/voice/command", json={"text": "good morning"}).json()["message"]
    assert "Secret meeting" in reply
