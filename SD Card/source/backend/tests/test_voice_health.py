from fastapi.testclient import TestClient

from luma.api import create_app
from luma.storage import Storage
from luma.voice_health import MAX_EVENTS, load_history, record
from luma.voice_speech import VoicePlaybackError


def test_voice_health_is_bounded_and_never_accepts_transcripts(tmp_path):
    storage = Storage(tmp_path / 'luma.db')
    history = []
    for index in range(MAX_EVENTS + 4):
        record(history, storage, kind='reply', engine='fallback',
               route='system_speaker', error='piper_start_failed')
    assert len(history) == MAX_EVENTS
    assert load_history(storage) == history
    saved = storage.get_cache('voice', 'health_history')
    assert len(saved) == MAX_EVENTS
    assert all(set(row) == {'kind', 'at', 'engine', 'route', 'error', 'primary_error'}
               for row in saved)
    assert 'secret spoken words' not in str(saved)
    try:
        record(history, storage, kind='reply', engine='fallback',
               error='secret spoken words')
    except ValueError:
        pass
    else:
        raise AssertionError('Arbitrary speech must not enter voice health storage')
    assert len(history) == MAX_EVENTS


def test_malformed_old_health_cache_is_ignored(tmp_path):
    storage = Storage(tmp_path / 'luma.db')
    storage.set_cache('voice', 'health_history', [
        {'kind': ['reply'], 'at': 'bad', 'engine': None,
         'route': None, 'error': None, 'primary_error': None},
        {'kind': 'reply', 'at': '2026-10-01T10:00:00+00:00',
         'engine': 'fallback', 'route': None, 'error': None,
         'primary_error': None, 'text': 'private'},
    ])
    assert load_history(storage) == []


def test_playback_health_survives_api_restart_without_speech_text(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        report = client.post('/api/v1/voice/output-report', json={
            'engine': 'fallback', 'route': 'system_speaker',
            'error': 'piper_start_failed', 'primary_error': 'piper_start_failed',
        })
        assert report.status_code == 200 and report.json()['accepted']
        assert client.post('/api/v1/voice/output-report', json={
            'engine': 'piper', 'route': 'system_speaker', 'text': 'private speech',
        }).status_code == 422
    with TestClient(create_app(data_dir=tmp_path)) as client:
        result = client.get('/api/v1/voice/asset').json()
        assert result['last_reply_engine'] == 'fallback'
        assert result['last_reply_primary_error'] == 'piper_start_failed'
        assert result['health_history'][-1]['kind'] == 'reply'
        assert result['last_reply_at'] == result['health_history'][-1]['at']
        assert 'text' not in str(result['health_history'])
        remote = TestClient(client.app, client=('192.168.1.7', 5000))
        assert remote.get('/api/v1/voice/asset').status_code == 403


def test_failed_speaker_check_remains_visible_after_api_restart(tmp_path, monkeypatch):
    import luma.api as api
    def fail_tone():
        raise VoicePlaybackError('speaker_route_unavailable')
    monkeypatch.setattr(api, 'play_test_tone', fail_tone)
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.post('/api/v1/voice/asset/tone').status_code == 409
    with TestClient(create_app(data_dir=tmp_path)) as client:
        status = client.get('/api/v1/voice/asset').json()
        assert status['last_tone_error'] == 'speaker_route_unavailable'
        assert status['health_history'][-1]['kind'] == 'tone'
        assert status['health_history'][-1]['error'] == 'speaker_route_unavailable'
