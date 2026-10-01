import json
import math

import pytest

from luma.voice_speaker import (SpeakerObservation, SpeakerVectorError,
                                decode_speaker_observation, speaker_similarity)

VOICE_FRAME = b'\xe8\x03\x18\xfc' * 2000  # 250 ms, alternating +/-1000.


def vector(index: int, size: int = 128) -> list[float]:
    values = [0.0] * size
    values[index] = 2.0
    return values


class FakeRecognizer:
    def __init__(self, endpoint: dict, final: dict):
        self.endpoint = endpoint
        self.final = final
        self.calls = 0

    def Reset(self):
        self.calls = 0

    def AcceptWaveform(self, _pcm):
        self.calls += 1
        return self.calls == 8

    def Result(self):
        return json.dumps(self.endpoint)

    def FinalResult(self):
        return json.dumps(self.final)


def test_speaker_trial_uses_longest_reported_vector_and_no_words():
    recognizer = FakeRecognizer(
        {'text': 'private words ignored', 'spk': vector(0), 'spk_frames': 275},
        {'text': 'more private words ignored', 'spk': vector(1), 'spk_frames': 80},
    )
    result = decode_speaker_observation(recognizer, [VOICE_FRAME] * 16)
    assert result.spk_frames == 275 and result.input_seconds == 4
    assert result.vector[0] == 1 and result.vector[1] == 0
    assert not hasattr(result, 'text') and not hasattr(result, 'audio')


@pytest.mark.parametrize('result', [
    {'spk': vector(0, 8), 'spk_frames': 100},
    {'spk': [0.0] * 128, 'spk_frames': 100},
    {'spk': [math.nan] * 128, 'spk_frames': 100},
    {'spk': [1e308] * 128, 'spk_frames': 100},
    {'spk': vector(0), 'spk_frames': 0},
    {'text': 'no speaker vector'},
])
def test_speaker_trial_rejects_unusable_vectors(result):
    recognizer = FakeRecognizer(result, result)
    with pytest.raises(SpeakerVectorError):
        decode_speaker_observation(recognizer, [VOICE_FRAME] * 16)


def test_speaker_trial_refuses_short_or_unbounded_audio():
    recognizer = FakeRecognizer({'spk': vector(0), 'spk_frames': 100}, {})
    with pytest.raises(SpeakerVectorError, match='four to eight'):
        decode_speaker_observation(recognizer, [VOICE_FRAME] * 8)
    with pytest.raises(SpeakerVectorError):
        decode_speaker_observation(recognizer, [VOICE_FRAME] * 33)
    with pytest.raises(SpeakerVectorError):
        decode_speaker_observation(recognizer, [b'odd'])


def test_speaker_trial_rejects_digital_silence_clipping_and_low_snr():
    recognizer = FakeRecognizer({'spk': vector(0), 'spk_frames': 100}, {})
    with pytest.raises(SpeakerVectorError, match='Too little speech'):
        decode_speaker_observation(recognizer, [b'\x00\x00' * 4000] * 16)
    with pytest.raises(SpeakerVectorError, match='clipped'):
        decode_speaker_observation(recognizer, [b'\xff\x7f' * 4000] * 16)
    with pytest.raises(SpeakerVectorError, match='Too little speech'):
        decode_speaker_observation(recognizer, [VOICE_FRAME] * 16, noise_rms=.02)


def test_speaker_similarity_is_cosine_without_magic_identity_threshold():
    a = SpeakerObservation((1.0, 0.0), 250, 4.0)
    b = SpeakerObservation((0.6, 0.8), 260, 4.5)
    c = SpeakerObservation((-1.0, 0.0), 300, 5.0)
    assert speaker_similarity(a, a) == 1
    assert speaker_similarity(a, b) == .6
    assert speaker_similarity(a, c) == -1
    assert speaker_similarity(SpeakerObservation((2.0, 0.0), 250, 4.0), b) == .6
    with pytest.raises(SpeakerVectorError):
        speaker_similarity(a, SpeakerObservation((1.0,), 200, 4.0))
    with pytest.raises(SpeakerVectorError):
        speaker_similarity(a, SpeakerObservation((math.nan, 0.0), 200, 4.0))
