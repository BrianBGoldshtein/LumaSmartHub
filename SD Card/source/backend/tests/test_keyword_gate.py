from array import array
import sys

import pytest

from luma.keyword_gate import first_sustained_sound, keyword_near_sound_start
from luma.keyword_wake import KeywordEvidence, KeywordWakeError
from luma.voice_wake import WakeAudioBuffer


def audio(*sections):
    pcm = array('h')
    for seconds, magnitude in sections:
        # Alternating sign ensures amplitude is not merely a DC offset.
        pcm.extend(magnitude if index%2 else -magnitude for index in range(int(16000*seconds)))
    if sys.byteorder != 'little':
        pcm.byteswap()
    data = pcm.tobytes()
    return [data[offset:offset+8000] for offset in range(0,len(data),8000)]


def test_quiet_preroll_does_not_impose_an_absolute_start_time():
    frames = audio((5,0), (.5,1000))
    assert first_sustained_sound(frames) == 5
    assert keyword_near_sound_start(KeywordEvidence(True,5), frames)
    assert not keyword_near_sound_start(KeywordEvidence(True,0), frames)


def test_keyword_deep_inside_conversation_is_not_a_wake_lead_in():
    frames = audio((4,1000))
    assert keyword_near_sound_start(KeywordEvidence(True,.6), frames)
    assert not keyword_near_sound_start(KeywordEvidence(True,1.36), frames)
    assert not keyword_near_sound_start(KeywordEvidence(True,3.64), frames)


def test_silence_or_one_short_impulse_does_not_create_an_onset():
    frames = audio((1,0), (.02,1000), (1,0))
    assert first_sustained_sound(frames) is None
    assert not keyword_near_sound_start(KeywordEvidence(True,1), frames)
    assert not keyword_near_sound_start(KeywordEvidence(False), audio((1,1000)))


def test_room_floor_is_respected_without_amplifying_noise():
    frames = audio((1,100), (1,1500))
    assert first_sustained_sound(frames,noise_rms=.004) == 1


@pytest.mark.parametrize('noise', [True, -.1, 1.1, float('nan'), float('inf'), 'quiet'])
def test_invalid_noise_configuration_fails_closed(noise):
    with pytest.raises(KeywordWakeError,match='keyword_noise_invalid'):
        first_sustained_sound(audio((1,1000)),noise_rms=noise)


def test_incomplete_buffer_cannot_be_revalidated_from_its_tail():
    frames = WakeAudioBuffer()
    for _ in range(37):
        frames.append(bytes(8000))
    with pytest.raises(KeywordWakeError,match='keyword_audio_invalid'):
        keyword_near_sound_start(KeywordEvidence(True,0), frames)


@pytest.mark.parametrize('timestamp', [True, -1, 5, float('nan'),float('inf')])
def test_invalid_evidence_never_passes_the_position_guard(timestamp):
    with pytest.raises(KeywordWakeError,match='keyword_result_invalid'):
        keyword_near_sound_start(KeywordEvidence(True,timestamp), audio((1,1000)))
