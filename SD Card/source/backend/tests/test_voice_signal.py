import math
import struct

import pytest

from luma.voice_signal import (AudioPreprocessor, AudioProfile, CalibrationSegmenter,
                               derive_profile, low_frequency_fraction, pcm_measurements,
                               read_profile, room_noise_level,
                               speech_measurements)


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


def test_speech_level_ignores_silent_tail_but_clipping_never_disappears():
    quiet = pcm(*([12] * 4000))
    voiced = pcm(*([1700, -1700] * 2000))
    frames = [quiet, voiced, voiced, *([quiet] * 6)]
    result = speech_measurements(frames, noise_rms=.001)
    assert result['rms'] > .05
    assert result['rms'] > pcm_measurements(b''.join(frames))['rms'] * 1.8
    clipped = pcm(*([32767] * 100 + [1700, -1700] * 1950))
    with_clip = speech_measurements([quiet, voiced, clipped, *([quiet] * 6)],
                                    noise_rms=.001)
    assert with_clip['peak'] > .995
    assert with_clip['clipped_fraction'] > .02
    with pytest.raises(ValueError):
        speech_measurements([], noise_rms=.001)


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


def test_clean_faint_speech_reaches_setup_trial_without_counting_room_noise():
    faint = sample_rows(rms=.0015, peak=.003)
    profile = derive_profile([.00015] * 4, faint)
    assert profile.quality == 'quiet' and profile.gain > 1
    assert derive_profile([.001] * 4, faint).quality == 'noisy'
    segmenter = CalibrationSegmenter()
    room = pcm(*([2] * 4000))
    weak_voice = pcm(*([100, -100] * 2000))
    assert segmenter.feed(room, room, noise_rms=.00015) is None
    assert segmenter.feed(weak_voice, weak_voice, noise_rms=.00015) is None
    assert segmenter.feed(weak_voice, weak_voice, noise_rms=.00015) is None
    assert segmenter.feed(room, room, noise_rms=.00015) is None
    assert segmenter.feed(room, room, noise_rms=.00015) is None
    captured = segmenter.feed(room, room, noise_rms=.00015)
    assert captured is not None
    measured = speech_measurements(captured[0], noise_rms=.00015)
    assert measured['peak'] >= .003 and measured['rms'] > .002
    assert CalibrationSegmenter().feed(room, room, noise_rms=.00015) is None


def test_unstable_room_floor_never_becomes_an_amplifying_profile():
    profile = derive_profile([.001, .0012, .0011, .006], sample_rows())
    assert profile.quality == 'unstable'
    assert profile.gain == 1 and not profile.high_pass
    assert read_profile(profile.public()).quality == 'unstable'
    assert read_profile({**profile.public(), 'gain': 2}).quality == 'unmeasured'
    clipped = derive_profile([.001, .0012, .0011, .006],
                             sample_rows(peak=.999, clipped=.01))
    assert clipped.quality == 'clipped'


def test_dc_bias_triggers_high_pass_without_removing_speech():
    profile = derive_profile([.001] * 5, sample_rows(rms=.08, peak=.5, dc=.03))
    assert profile.high_pass and profile.gain == 1
    processor = AudioPreprocessor(profile)
    biased = pcm(*([4000] * 4000))
    first = processor.process(biased)
    second = processor.process(biased)
    assert pcm_measurements(second)['dc'] < pcm_measurements(first)['dc']


def test_room_rumble_selects_high_pass_but_higher_frequency_noise_does_not():
    def tone(hz: int) -> bytes:
        return pcm(*(round(1000 * math.sin(2 * math.pi * hz * index / 16000))
                     for index in range(4000)))

    rumble = low_frequency_fraction(tone(60))
    higher = low_frequency_fraction(tone(500))
    assert rumble > .30
    assert higher < .10
    speech = sample_rows(rms=.07, peak=.4)
    selected = derive_profile([.002] * 4, speech,
                              room_low_fractions=[rumble] * 4)
    ignored = derive_profile([.002] * 4, speech,
                             room_low_fractions=[higher] * 4)
    assert selected.high_pass and selected.gain == 1
    assert not ignored.high_pass
    assert read_profile(selected.public()).high_pass
    assert read_profile({**selected.public(), 'low_frequency_noise_fraction': 2}).quality == 'unmeasured'


def test_room_rumble_does_not_override_noisy_or_clipped_source():
    noisy = derive_profile([.02] * 4, sample_rows(rms=.05),
                           room_low_fractions=[.8] * 4)
    clipped = derive_profile([.002] * 4, sample_rows(peak=.99, clipped=.01),
                             room_low_fractions=[.8] * 4)
    assert noisy.quality == 'noisy' and not noisy.high_pass
    assert clipped.quality == 'clipped' and not clipped.high_pass
    with pytest.raises(ValueError):
        low_frequency_fraction(b'\x01')


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


def test_saved_gain_is_effective_from_first_wake_frame_but_loud_audio_is_limited():
    processor = AudioPreprocessor(AudioProfile(gain=2, quality='quiet'))
    wake_start = pcm(*([1000, -1000] * 2000))
    assert processor.process(wake_start) == pcm(*([2000, -2000] * 2000))
    processor.reset()
    assert processor.process(wake_start) == pcm(*([2000, -2000] * 2000))
    processor.reset()
    sudden_loud = pcm(*([32000, -32000] * 2000))
    assert pcm_measurements(processor.process(sudden_loud))['peak'] <= .901
    assert processor.applied_gain < 1


def test_high_pass_boundary_transient_is_limited_before_recognition():
    processor = AudioPreprocessor(AudioProfile(gain=2, high_pass=True,
                                               quality='quiet'))
    # The first frame leaves a large previous_input in the filter state.
    # The next raw frame is digital silence, yet its first filtered sample
    # swings downward. Raw-peak-only limiting clipped this boundary.
    processor.process(pcm(*([20000] * 4000)))
    quiet = pcm(*([0] * 4000))
    processed = processor.process(quiet)
    assert pcm_measurements(quiet)['peak'] == 0
    assert .4 < pcm_measurements(processed)['peak'] <= .901
    assert pcm_measurements(processed)['clipped_fraction'] == 0


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
