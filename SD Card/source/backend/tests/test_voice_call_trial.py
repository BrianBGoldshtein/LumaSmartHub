import json

import pytest
from fastapi.testclient import TestClient

from luma.api import create_app
from luma.voice_agent import call_trial_decoding_payload
from luma.voice_call_trial import VoiceCallTrial


def test_call_trial_counts_only_bounded_boolean_observations_and_expires():
    trial = VoiceCallTrial()
    session = trial.start(100)['session']
    assert trial.status(100)['remaining_seconds'] == 90
    trial.record(session, partial_wake=False, constrained_wake=False, constrained_near_start=False,
                 free_wake=False, free_near_start=False, now=101)
    trial.record(session, partial_wake=True, constrained_wake=False, constrained_near_start=False,
                 free_wake=False, free_near_start=False, now=101.5)
    trial.record(session, partial_wake=True, constrained_wake=True, constrained_near_start=True,
                 free_wake=False, free_near_start=False, now=102)
    trial.record(session, partial_wake=False, constrained_wake=True, constrained_near_start=True,
                 free_wake=True, free_near_start=True, now=103)
    result = trial.record(session, partial_wake=True, constrained_wake=True, constrained_near_start=False,
                          free_wake=True, free_near_start=False, now=104)
    assert result['utterances'] == 5
    assert result['partial_wakes'] == 3
    assert result['constrained_wakes'] == 3
    assert result['dual_wakes'] == result['quoted_wakes'] == 1
    assert not any(key in json.dumps(result) for key in ('transcript', 'audio', 'text'))
    with pytest.raises(ValueError):
        trial.record(session, partial_wake=False, constrained_wake=False, constrained_near_start=False,
                     free_wake=True, free_near_start=False, now=105)
    with pytest.raises(ValueError):
        trial.record(session, partial_wake=False, constrained_wake=True, constrained_near_start=1,
                     free_wake=True, free_near_start=True, now=105)
    assert not trial.status(190)['active']
    with pytest.raises(ValueError):
        trial.record(session, partial_wake=False, constrained_wake=False, constrained_near_start=False,
                     free_wake=False, free_near_start=False, now=190)
    assert trial.start(191)['utterances'] == 0


class FakeRecognizer:
    def __init__(self, text):
        self.text = text
        self.calls = 0

    def Reset(self):
        self.calls += 1

    def AcceptWaveform(self, _frame):
        self.calls += 1
        return False

    def FinalResult(self):
        self.calls += 1
        return json.dumps({'text': self.text})


def test_call_trial_decoder_sends_no_words_and_skips_unneeded_replay():
    free = FakeRecognizer('hey luma what time is it')
    plain = call_trial_decoding_payload('ordinary call speech', free, [b'frame'], 'hey luma')
    assert plain == {'partial_wake': False, 'constrained_wake': False, 'constrained_near_start': False,
                     'free_wake': False, 'free_near_start': False}
    assert free.calls == 0
    quoted = call_trial_decoding_payload('someone quoted hey luma later', free,
                                         [b'frame'], 'hey luma', partial_wake=True)
    assert quoted == {'partial_wake': True, 'constrained_wake': True, 'constrained_near_start': False,
                      'free_wake': True, 'free_near_start': True}
    assert free.calls == 3
    assert 'text' not in quoted and 'audio' not in quoted


def test_same_call_audio_reports_whether_tuning_created_a_dual_false_wake():
    processed_free = FakeRecognizer('hey luma what time is it')
    untouched_constrained = FakeRecognizer('ordinary call speech')
    observation = call_trial_decoding_payload(
        'hey luma what time is it', processed_free, [b'processed'], 'hey luma',
        raw_spoken=[b'untouched'], constrained=untouched_constrained)
    assert observation['raw_compared'] is True
    assert observation['constrained_near_start'] and observation['free_near_start']
    assert observation['raw_constrained_wake'] is False
    assert observation['raw_free_wake'] is False
    assert 'text' not in observation and 'audio' not in observation
    trial = VoiceCallTrial()
    session = trial.start(100)['session']
    status = trial.record(session, **observation, now=101)
    assert status['raw_compared_utterances'] == 1
    assert status['processed_dual_compared'] == 1
    assert status['tuned_only_dual_wakes'] == 1
    assert status['raw_only_dual_wakes'] == 0
    assert status['raw_dual_wakes'] == 0
    with pytest.raises(ValueError, match='raw'):
        trial.record(session, **{**observation, 'raw_free_wake': True}, now=102)
    assert trial.status(102)['utterances'] == 1


def test_raw_only_wake_is_counted_separately_and_no_tuning_skips_replay():
    free = FakeRecognizer('hey luma what time is it')
    raw_constrained = FakeRecognizer('hey luma what time is it')
    observation = call_trial_decoding_payload(
        'ordinary call speech', free, [b'processed'], 'hey luma',
        raw_spoken=[b'untouched'], constrained=raw_constrained)
    trial = VoiceCallTrial()
    session = trial.start(100)['session']
    status = trial.record(session, **observation, now=101)
    assert status['raw_dual_wakes'] == status['raw_only_dual_wakes'] == 1
    assert status['processed_dual_compared'] == 0
    assert status['tuned_only_dual_wakes'] == 0
    without_tuning = call_trial_decoding_payload('ordinary call speech', free,
                                                  [b'processed'], 'hey luma')
    assert 'raw_compared' not in without_tuning
    assert trial.record(session, **without_tuning, now=102)['raw_compared_utterances'] == 1


def test_owner_local_call_trial_blocks_commands_and_keeps_no_saved_results(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.post('/api/v1/voice/call-trial/start').status_code == 409
        assert client.post('/api/v1/voice/heartbeat', json={}).json()['accepted']
        started = client.post('/api/v1/voice/call-trial/start')
        assert started.status_code == 200
        session = started.json()['session']
        assert client.post('/api/v1/voice/calibration/start').status_code == 409
        blocked = client.post('/api/v1/voice/command', json={'text': 'good morning'})
        assert blocked.status_code == 200 and blocked.json()['accepted'] is False
        observation = {'session': session, 'partial_wake': True, 'constrained_wake': True,
                       'constrained_near_start': True, 'free_wake': False,
                       'free_near_start': False}
        assert client.post('/api/v1/voice/call-trial/observation', json=observation).status_code == 200
        assert client.get('/api/v1/voice/call-trial').json()['constrained_wakes'] == 1
        assert client.get('/api/v1/voice/call-trial').json()['partial_wakes'] == 1
        compared = {**observation, 'raw_compared': True,
                    'raw_constrained_wake': False,
                    'raw_constrained_near_start': False,
                    'raw_free_wake': False, 'raw_free_near_start': False}
        assert client.post('/api/v1/voice/call-trial/observation', json=compared).status_code == 200
        assert client.get('/api/v1/voice/call-trial').json()['raw_compared_utterances'] == 1
        assert client.post('/api/v1/voice/call-trial/stop').json()['active'] is False
        assert client.post('/api/v1/voice/call-trial/observation', json=observation).status_code == 409
        remote = TestClient(client.app, client=('192.168.1.7', 5000))
        assert remote.post('/api/v1/voice/call-trial/start').status_code == 403
    with TestClient(create_app(data_dir=tmp_path)) as restarted:
        assert restarted.get('/api/v1/voice/call-trial').json()['session'] == ''
