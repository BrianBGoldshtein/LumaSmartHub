from fastapi.testclient import TestClient
import time

from luma.api import create_app


def test_optional_model_requires_local_explicit_consent_and_never_auto_downloads(tmp_path, monkeypatch):
    state = {'ready': False, 'calls': 0}
    monkeypatch.setattr('luma.api.speaker_model_ready', lambda _root: state['ready'])
    def install(_root):
        state['calls'] += 1
        state['ready'] = True
    monkeypatch.setattr('luma.api.install_speaker_model', install)
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.get('/api/v1/voice/speaker-trial').json()['model_ready'] is False
        assert state['calls'] == 0
        assert client.post('/api/v1/voice/speaker-trial/model/install').status_code == 422
        assert client.post('/api/v1/voice/speaker-trial/model/install',
                           json={'confirmed': False}).status_code == 422
        remote = TestClient(client.app, client=('192.168.1.7', 5000))
        assert remote.post('/api/v1/voice/speaker-trial/model/install',
                           json={'confirmed': True}).status_code == 403
        assert state['calls'] == 0
        assert client.post('/api/v1/voice/speaker-trial/model/install',
                           json={'confirmed': True}).status_code == 200
        for _ in range(40):
            if client.get('/api/v1/voice/speaker-trial').json()['model_phase'] == 'ready':
                break
            time.sleep(.025)
        assert state['calls'] == 1
        assert client.get('/api/v1/voice/speaker-trial').json()['model_ready'] is True


def test_owner_local_speaker_trial_consent_and_command_suppression(tmp_path, monkeypatch):
    monkeypatch.setattr('luma.api.speaker_model_ready', lambda _root: True)
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.post('/api/v1/voice/speaker-trial/start', json={'confirmed': True}).status_code == 409
        assert client.post('/api/v1/voice/heartbeat', json={}).status_code == 200
        assert client.post('/api/v1/voice/speaker-trial/start').status_code == 422
        started = client.post('/api/v1/voice/speaker-trial/start', json={'confirmed': True})
        assert started.status_code == 200
        session = started.json()['session']
        assert started.json()['role'] == 'enrollment'
        assert client.post('/api/v1/voice/calibration/start').status_code == 409
        assert client.post('/api/v1/voice/call-trial/start').status_code == 409
        blocked = client.post('/api/v1/voice/command', json={'text': 'good morning'})
        assert blocked.status_code == 200 and blocked.json()['accepted'] is False
        armed = client.post('/api/v1/voice/speaker-trial/begin', json={'session': session})
        assert armed.status_code == 200 and armed.json()['phase'] == 'arming'
        token = armed.json()['token']
        assert client.post('/api/v1/voice/speaker-trial/armed', json={
            'session': session, 'token': token}).status_code == 200
        failed = client.post('/api/v1/voice/speaker-trial/observation', json={
            'session': session, 'token': token, 'error': 'too_quiet'})
        assert failed.status_code == 200 and failed.json()['completed'] == 0
        assert failed.json()['last_error'] == 'too_quiet'
        assert client.post('/api/v1/voice/speaker-trial/cancel', json={
            'session': session}).json()['phase'] == 'cancelled'
        assert client.post('/api/v1/voice/command', json={
            'text': 'what time is it'}).json()['accepted'] is True
        remote = TestClient(client.app, client=('192.168.1.7', 5000))
        assert remote.post('/api/v1/voice/speaker-trial/start',
                           json={'confirmed': True}).status_code == 403
    with TestClient(create_app(data_dir=tmp_path)) as restarted:
        assert restarted.get('/api/v1/voice/speaker-trial').json()['session'] == ''


def test_turning_off_microphone_cancels_and_discards_speaker_trial(tmp_path, monkeypatch):
    monkeypatch.setattr('luma.api.speaker_model_ready', lambda _root: True)
    with TestClient(create_app(data_dir=tmp_path)) as client:
        client.post('/api/v1/voice/heartbeat', json={})
        started = client.post('/api/v1/voice/speaker-trial/start',
                              json={'confirmed': True}).json()
        assert started['active']
        assert client.patch('/api/v1/settings', json={'voice_enabled': False}).status_code == 200
        status = client.get('/api/v1/voice/speaker-trial').json()
        assert status['phase'] == 'cancelled' and not status['active']
        assert client.post('/api/v1/voice/speaker-trial/begin', json={
            'session': started['session']}).status_code == 409
