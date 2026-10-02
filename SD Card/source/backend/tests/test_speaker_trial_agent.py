import json
import queue
from array import array

from luma.voice_agent import collect_speaker_trial_frames, speaker_trial_result


FRAME = array('h', [2000] * 4000).tobytes()


class Capture:
    dropped_frames = 0
    def stalled(self):
        return False


class Recognizer:
    def Reset(self):
        pass
    def AcceptWaveform(self, _frame):
        return False
    def FinalResult(self):
        return json.dumps({'spk': [1.0] + [0.0] * 127, 'spk_frames': 500,
                           'text': 'private words are discarded'})


def test_speaker_trial_capture_and_decode_never_return_audio_or_words():
    chunks = queue.Queue()
    for _ in range(24):
        chunks.put(FRAME)
    frames, error = collect_speaker_trial_frames(chunks, Capture())
    assert error is None and len(frames) == 24
    result = speaker_trial_result(Recognizer(), frames, noise_rms=.001)
    assert len(result['vector']) == 128 and result['spk_frames'] == 500
    assert result['input_seconds'] == 6
    assert 'text' not in result and 'audio' not in result and 'pcm' not in result
    frames.clear()


def test_speaker_trial_rejects_capture_failure_and_quiet_samples():
    chunks = queue.Queue()
    chunks.put(None)
    assert collect_speaker_trial_frames(chunks, Capture()) == ([], 'capture_stopped')
    chunks = queue.Queue()
    chunks.put(b'partial')
    assert collect_speaker_trial_frames(chunks, Capture()) == ([], 'capture_gap')
    assert speaker_trial_result(Recognizer(), [bytes(8000)] * 24,
                                noise_rms=.001) == {'error': 'too_quiet'}
