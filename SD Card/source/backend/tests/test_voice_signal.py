import math
import struct

import pytest

from luma.voice_signal import (AudioPreprocessor, AudioProfile, CalibrationSegmenter,
                               derive_profile, pcm_measurements, read_profile, room_noise_level)


def pcm(*samples: int) -> bytes:
    return struct.pack('<' + 'h' * len(samples), *samples)


def sample_rows(*, rms=.025, peak=.25, dc=0.0, clipped=0.0):
    return [{'matched': True, 'rms': rms, 'peak': peak,
             'dc': dc, 'clipped_fraction': clipped} for _ in range(8)]


def test_raw_pcm_measurements_detect_level_clipping_and_bias():
    result = pcm_measurements(pcm(0, 32767, -32768, 1000))
    assert result['peak'] == 1
    assert result['clipped_fraction'] == .5
    assert 0 < result['rms'] < 1
    assert result['dc'] < .02
    with pytest.raises(ValueError):
        pcm_measurements(b'\x01')


def test_profile_amplifies_only_clean_quiet_speech():
    clean = derive_profile([.001, .0015, .002, .001], sample_rows())
    assert clean.quality == 'quiet'
    assert 1 < clean.gain <= 2
    assert clean.snr_db is not None and clean.snr_db > 15
    noisy = derive_profile([.017] * 5, sample_rows(rms=.03))
    assert noisy.quality == 'noisy' and noisy.gain == 1
    clipped = derive_profile([.001] * 5, sample_rows(peak=.97, clipped=.01))
    assert clipped.quality == 'clipped' and clipped.gain == 1
    intermittently_clipped = sample_rows()
    intermittently_clipped[4] = {**intermittently_clipped[4], 'peak': 1,
                                 'clipped_fraction': .01}
    assert derive_profile([.001] * 5, intermittently_clipped).quality == 'clipped'
    insufficient = derive_profile([.001], sample_rows())
    assert insufficient.quality == 'bypass' and insufficient.gain == 1
    missed_words = [{**item, 'matched': False} for item in sample_rows()]
    assert derive_profile([.001] * 5, missed_words).gain > 1
    mixed_room = [.001, .001, .025, .025]
    assert room_noise_level(mixed_room) == .025
    assert derive_profile(mixed_room, sample_rows()).quality == 'noisy'


def test_dc_bias_triggers_high_pass_without_removing_speech():
    profile = derive_profile([.001] * 5, sample_rows(rms=.08, peak=.5, dc=.03))
    assert profile.high_pass and profile.gain == 1
    processor = AudioPreprocessor(profile)
    biased = pcm(*([4000] * 4000))
    first = processor.process(biased)
    second = processor.process(biased)
    assert pcm_measurements(second)['dc'] < pcm_measurements(first)['dc']


def test_processing_is_bounded_and_default_is_bit_identical():
    raw = pcm(*([0, 2000, -2000, 0] * 1000))
    assert AudioPreprocessor().process(raw) == raw
    processor = AudioPreprocessor(AudioProfile(gain=2, quality='quiet'))
    boosted = processor.process(raw)
    assert len(boosted) == len(raw)
    assert pcm_measurements(boosted)['rms'] > pcm_measurements(raw)['rms']
    loud = pcm(*([32000, -32000] * 2000))
    assert pcm_measurements(processor.process(loud))['peak'] <= 1
    with pytest.raises(ValueError):
        processor.process(b'\x00')


def test_saved_profile_is_strictly_validated():
    profile = derive_profile([.001] * 5, sample_rows()).public()
    assert read_profile(profile).gain > 1
    assert read_profile({**profile, 'gain': 100}).gain == 1
    assert read_profile({**profile, 'gain': math.nan}).gain == 1
    assert read_profile({**profile, 'high_pass': 'yes'}).gain == 1
    assert read_profile({**profile, 'quality': 'arbitrary'}).gain == 1


def test_calibration_segments_speech_without_a_recognizer_endpoint():
    segmenter = CalibrationSegmenter()
    quiet = pcm(*([12] * 4000))
    voiced = pcm(*([1700, -1700] * 2000))
    assert segmenter.feed(quiet, quiet, noise_rms=.0004) is None
    assert segmenter.feed(voiced, voiced, noise_rms=.0004) is None
    assert segmenter.feed(voiced, voiced, noise_rms=.0004) is None
    assert segmenter.feed(voiced, voiced, noise_rms=.0004) is None
    assert segmenter.feed(quiet, quiet, noise_rms=.0004) is None
    assert segmenter.feed(quiet, quiet, noise_rms=.0004) is None
    captured = segmenter.feed(quiet, quiet, noise_rms=.0004)
    assert captured is not None
    raw, processed = captured
    assert len(raw) == len(processed) == 7
    assert pcm_measurements(b''.join(raw))['rms'] > .01
    assert segmenter.frames == []


def test_calibration_rejects_transient_noise_and_bounds_continuous_speech():
    segmenter = CalibrationSegmenter()
    quiet = pcm(*([16] * 4000))
    voiced = pcm(*([2000, -2000] * 2000))
    assert segmenter.feed(voiced, voiced, noise_rms=.001) is None
    for _ in range(4):
        assert segmenter.feed(quiet, quiet, noise_rms=.001) is None
    completed = None
    for _ in range(30):
        completed = segmenter.feed(voiced, voiced, noise_rms=.001)
        if completed is not None:
            break
    assert completed is not None
    assert len(completed[0]) <= 28
    assert segmenter.frames == []
    with pytest.raises(ValueError):
        segmenter.feed(b'bad', b'bad', noise_rms=.001)
