import math
import time

import pytest

from luma.speaker_trial import SpeakerTrial, STEPS
from luma.voice_speaker import SpeakerVectorError


def vector(index: int, *, other: bool = False) -> list[float]:
    values = [0.0] * 128
    values[1 if other else 0] = 1.0
    values[2 + index] = .02 * (index + 1)
    size = math.sqrt(sum(value * value for value in values))
    return [value / size for value in values]


def test_trial_requires_explicit_independent_samples_and_keeps_only_scores():
    trial = SpeakerTrial()
    started = trial.start()
    assert started['active'] and started['completed'] == 0
    assert started['report'] is None
    assert trial.status()['role'] == 'enrollment'
    for index, (role, _prompt) in enumerate(STEPS):
        armed = trial.begin(started['session'])
        assert armed['phase'] == 'arming' and armed['role'] == role
        with pytest.raises(SpeakerVectorError, match='no longer being recorded'):
            trial.submit(started['session'], armed['token'], vector=vector(index),
                         spk_frames=100, input_seconds=6)
        trial.armed(started['session'], armed['token'])
        done = trial.submit(started['session'], armed['token'],
                            vector=vector(index, other=index >= 5),
                            spk_frames=100, input_seconds=6)
        assert done['completed'] == index + 1
        if index == len(STEPS) - 1:
            assert all(not value for value in trial._samples.values())
    assert done['phase'] == 'complete' and not done['active']
    assert done['report']['observed_separation'] is True
    assert done['report']['candidate_threshold'] is not None
    assert 'vector' not in str(done) and 'audio' not in str(done)
    assert all(not samples for samples in trial._samples.values())


def test_failed_sample_can_retry_without_advancing_or_retaining_audio():
    trial = SpeakerTrial()
    session = trial.start()['session']
    first = trial.begin(session)
    trial.armed(session, first['token'])
    failed = trial.submit(session, first['token'], error='too_quiet')
    assert failed['phase'] == 'ready' and failed['completed'] == 0
    assert failed['last_error'] == 'too_quiet'
    with pytest.raises(SpeakerVectorError, match='no longer being recorded'):
        trial.submit(session, first['token'], vector=vector(0), spk_frames=100,
                     input_seconds=6)
    second = trial.begin(session)
    assert second['token'] != first['token']
    trial.armed(session, second['token'])
    assert trial.submit(session, second['token'], vector=vector(0),
                        spk_frames=100, input_seconds=6)['completed'] == 1
    assert trial.cancel()['phase'] == 'cancelled'
    assert all(not samples for samples in trial._samples.values())


def test_trial_rejects_duplicate_vectors_invalid_values_and_stale_tokens():
    trial = SpeakerTrial()
    session = trial.start()['session']
    first = trial.begin(session)
    trial.armed(session, first['token'])
    for bad in ([float('nan')] * 128, [0.0] * 128, [1.0] * 40):
        with pytest.raises(SpeakerVectorError):
            trial.submit(session, first['token'], vector=bad, spk_frames=100,
                         input_seconds=6)
    trial.submit(session, first['token'], vector=vector(0), spk_frames=100,
                 input_seconds=6)
    second = trial.begin(session)
    trial.armed(session, second['token'])
    with pytest.raises(SpeakerVectorError, match='independent'):
        trial.submit(session, second['token'], vector=vector(0),
                     spk_frames=100, input_seconds=6)
    with pytest.raises(SpeakerVectorError, match='Invalid speaker'):
        trial.submit(session, second['token'], error='arbitrary_private_error')
    assert trial.status()['completed'] == 1


def test_trial_expires_and_discards_biometrics():
    trial = SpeakerTrial()
    now = time.monotonic()
    session = trial.start(now=now)['session']
    first = trial.begin(session, now=now + 1)
    trial.armed(session, first['token'], now=now + 2)
    trial.submit(session, first['token'], vector=vector(0),
                 spk_frames=100, input_seconds=6, now=now + 3)
    assert trial.status(now=now + 901)['phase'] == 'expired'
    assert all(not samples for samples in trial._samples.values())
    with pytest.raises(SpeakerVectorError):
        trial.begin(session, now=now + 902)
