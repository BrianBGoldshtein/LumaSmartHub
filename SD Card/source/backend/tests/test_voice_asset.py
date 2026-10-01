import hashlib
import io
import json
from pathlib import Path
import subprocess
import struct
import threading
import time
from types import SimpleNamespace
import wave
import zipfile

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient

from luma.api import create_app
from luma.voice_asset import (CONFIG, MODEL, PREVIOUS_VOICE, VOICE_ID, VOICE_ASSET_NAME,
                              VOICE_RELEASE_URL, VoiceAssetError, fetch_and_install,
                              install_asset, ready, recover_interrupted_repair,
                              verify_and_extract, voice_status, write_status)
from luma.voice_speech import OfflineSpeaker, VoicePlaybackError, fallback_wav_to_pcm, play_test_tone, pulse_playback_environment, wav_to_pcm


def make_asset(tmp_path: Path, *, corrupt=False, extra=None):
    key = Ed25519PrivateKey.generate()
    public = tmp_path / "update.pub"
    public.write_bytes(key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    payload = {MODEL: b"model-bytes", CONFIG: b'{}', "sources/piper_tts-1.8.0.tar.gz": b"source archive",
               "wheels/piper_tts-1.8.0-cp39-abi3-manylinux2014_aarch64.whl": b"wheel"}
    if extra:
        payload.update(extra)
    manifest = {"format": 1, "kind": "luma-offline-voice", "version": "0.2.4",
                "voice_id": "en_US-kristin-medium", "python": "cp313-aarch64",
                "files": {name: {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
                          for name, data in payload.items()}}
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    archive = tmp_path / "voice.lva"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("manifest.json", raw)
        output.writestr("manifest.sig", key.sign(raw))
        for name, data in payload.items():
            output.writestr(name, data + (b"tampered" if corrupt and name == MODEL else b""))
    return archive, public


def test_signed_voice_package_extracts_only_verified_files(tmp_path):
    package, public = make_asset(tmp_path)
    staging = tmp_path / "stage"
    staging.mkdir()
    assert verify_and_extract(package, staging, public)["version"] == "0.2.4"
    assert (staging / MODEL).read_bytes() == b"model-bytes"


def test_voice_package_rejects_tampered_model(tmp_path):
    package, public = make_asset(tmp_path, corrupt=True)
    staging = tmp_path / "stage"
    staging.mkdir()
    with pytest.raises(VoiceAssetError):
        verify_and_extract(package, staging, public)


def test_voice_package_rejects_path_traversal_even_if_signed(tmp_path):
    package, public = make_asset(tmp_path, extra={"../../outside": b"malicious"})
    staging = tmp_path / "stage"
    staging.mkdir()
    with pytest.raises(VoiceAssetError, match="file list"):
        verify_and_extract(package, staging, public)
    assert not (tmp_path / "outside").exists()


def test_voice_package_rejects_extra_unsigned_member(tmp_path):
    package, public = make_asset(tmp_path)
    with zipfile.ZipFile(package, "a") as output:
        output.writestr("wheels/extra.whl", b"not signed")
    staging = tmp_path / "stage"
    staging.mkdir()
    with pytest.raises(VoiceAssetError, match="file list"):
        verify_and_extract(package, staging, public)


def test_voice_status_and_preview_are_local_and_do_not_install_automatically(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        status = client.get('/api/v1/voice/asset')
        assert status.status_code == 200 and status.json()['phase'] == 'checking'
        assert client.post('/api/v1/voice/asset/preview').status_code == 409
        assert client.post('/api/v1/voice/asset/retry').status_code == 409
    assert not (tmp_path / 'voice-assets').exists()


def test_system_service_resolves_the_users_pulse_socket(monkeypatch):
    import luma.voice_speech as speech
    monkeypatch.setattr(speech, 'sys', SimpleNamespace(platform='linux'))
    monkeypatch.setattr(speech, 'os', SimpleNamespace(environ={'PATH': '/usr/bin'}, getuid=lambda: 1007))
    monkeypatch.setattr(Path, 'is_socket', lambda self: True)
    env = pulse_playback_environment()
    assert env['XDG_RUNTIME_DIR'] == '/run/user/1007'
    assert env['PULSE_SERVER'] == 'unix:/run/user/1007/pulse/native'
    assert env['PULSE_SINK'] == 'luma_speaker'
    monkeypatch.setattr(Path, 'is_socket', lambda self: False)
    with pytest.raises(VoicePlaybackError, match='audio_session_unavailable'):
        pulse_playback_environment()


def test_tone_checks_named_sink_and_sends_bounded_pcm(monkeypatch):
    import luma.voice_speech as speech
    monkeypatch.setattr(speech, 'pulse_playback_environment', lambda: {'PULSE_SINK': 'luma_speaker'})
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        if command[:3] == ['pactl', 'list', 'short']:
            return SimpleNamespace(stdout='0\tluma_speaker\tPipeWire\ts16le 2ch 48000Hz\n')
        if command[:2] == ['pactl', 'get-default-sink']:
            return SimpleNamespace(stdout='luma_speaker\n')
        return SimpleNamespace()
    monkeypatch.setattr(speech.subprocess, 'run', run)
    assert play_test_tone() == 'luma_speaker'
    assert [call[0][0] for call in calls] == ['pactl', 'pactl', 'pacat']
    assert '--device=luma_speaker' in calls[2][0]
    assert len(calls[2][1]['input']) == 2 * int(22050 * .65)
    assert calls[2][1]['env']['PULSE_SINK'] == 'luma_speaker'


def test_tone_refuses_to_claim_success_without_named_sink(monkeypatch):
    import luma.voice_speech as speech
    monkeypatch.setattr(speech, 'pulse_playback_environment', lambda: {})
    calls = []
    def run(command, **_kwargs):
        calls.append(command[0])
        return SimpleNamespace(stdout='0\tother_output\tPipeWire\n')
    monkeypatch.setattr(speech.subprocess, 'run', run)
    with pytest.raises(VoicePlaybackError, match='speaker_route_unavailable'):
        play_test_tone()
    assert calls == ['pactl', 'pactl']


def test_tone_uses_selected_local_alsa_when_virtual_sink_missing(monkeypatch):
    import luma.voice_speech as speech
    monkeypatch.setattr(speech, 'pulse_playback_environment', lambda: {})
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        if command[:3] == ['pactl', 'list', 'short']:
            return SimpleNamespace(stdout='0\talsa_output.platform-hdmi\tPipeWire\n')
        if command[:2] == ['pactl', 'get-default-sink']:
            return SimpleNamespace(stdout='alsa_output.platform-hdmi\n')
        return SimpleNamespace()
    monkeypatch.setattr(speech.subprocess, 'run', run)
    assert play_test_tone() == 'system_speaker'
    assert '--device=alsa_output.platform-hdmi' in calls[-1][0]


def test_tone_prefers_selected_physical_sink_then_tries_virtual_sink(monkeypatch):
    import luma.voice_speech as speech
    monkeypatch.setattr(speech, 'pulse_playback_environment', lambda: {})
    played = []
    def run(command, **_kwargs):
        if command[:3] == ['pactl', 'list', 'short']:
            return SimpleNamespace(stdout='0\tluma_speaker\tPipeWire\n1\talsa_output.platform-hdmi\tPipeWire\n')
        if command[:2] == ['pactl', 'get-default-sink']:
            return SimpleNamespace(stdout='alsa_output.platform-hdmi\n')
        played.append(command)
        if '--device=alsa_output.platform-hdmi' in command:
            raise subprocess.CalledProcessError(1, command)
        return SimpleNamespace()
    monkeypatch.setattr(speech.subprocess, 'run', run)
    assert play_test_tone() == 'luma_speaker'
    assert len(played) == 2
    assert '--device=alsa_output.platform-hdmi' in played[0]
    assert '--device=luma_speaker' in played[-1]


def test_tone_never_falls_back_to_bluetooth_default(monkeypatch):
    import luma.voice_speech as speech
    monkeypatch.setattr(speech, 'pulse_playback_environment', lambda: {})
    def run(command, **_kwargs):
        if command[:3] == ['pactl', 'list', 'short']:
            return SimpleNamespace(stdout='0\tbluez_output.phone\tPipeWire\n')
        return SimpleNamespace(stdout='bluez_output.phone\n')
    monkeypatch.setattr(speech.subprocess, 'run', run)
    with pytest.raises(VoicePlaybackError, match='speaker_route_unavailable'):
        play_test_tone()


def test_piper_failure_reports_actual_fallback_engine(monkeypatch, tmp_path):
    import luma.voice_speech as speech
    monkeypatch.setattr(speech, 'sys', SimpleNamespace(platform='linux'))
    monkeypatch.setattr(speech, 'ready', lambda _root: True)
    calls = []
    monkeypatch.setattr(speech.subprocess, 'run', lambda *args, **kwargs: (calls.append((args, kwargs)) or SimpleNamespace(stdout=b'fake')))
    monkeypatch.setattr(speech, 'fallback_wav_to_pcm', lambda _data: (b'\x00\x00' * 10, 22050))
    monkeypatch.setattr(speech, 'pulse_playback_environment', lambda: {})
    monkeypatch.setattr(speech, '_play_pcm', lambda _pcm, _env, **_kwargs: 'system_speaker')
    speaker = OfflineSpeaker(tmp_path)
    def fail(_reply):
        raise VoicePlaybackError('speaker_route_unavailable')
    monkeypatch.setattr(speaker, '_piper', fail)
    assert speaker.speak('Hello.') == 'fallback'
    assert speaker.last_error == 'speaker_route_unavailable'
    assert speaker.last_primary_error == 'speaker_route_unavailable'
    assert speaker.last_route == 'system_speaker'
    assert calls[0][0][0][0] == 'espeak-ng'
    assert '--stdout' in calls[0][0][0]
    assert speaker.speak('Again.') == 'fallback'
    assert speaker.last_error == 'speaker_route_unavailable'
    assert speaker.last_primary_error == 'speaker_route_unavailable'


def test_voice_repair_clears_old_worker_cooldown(monkeypatch, tmp_path):
    import luma.voice_speech as speech
    monkeypatch.setattr(speech, 'sys', SimpleNamespace(platform='linux'))
    monkeypatch.setattr(speech, 'ready', lambda _root: True)
    folder = tmp_path / VOICE_ID / 'model'
    folder.mkdir(parents=True)
    model = folder / f'{VOICE_ID}.onnx'
    model.write_bytes(b'old')
    speaker = OfflineSpeaker(tmp_path)
    speaker._refresh_asset_identity()
    speaker.retry_after = speech.monotonic() + 120
    speaker.failure_cause = 'piper_start_failed'
    model.write_bytes(b'new signed model')
    attempted = []
    def use_piper(_reply):
        attempted.append(True)
        speaker.last_route = 'system_speaker'
    monkeypatch.setattr(speaker, '_piper', use_piper)
    assert speaker.speak('Hello.') == 'piper'
    assert attempted and speaker.retry_after == 0


def test_preview_failure_is_explicit_and_local(monkeypatch, tmp_path):
    import luma.api as api
    monkeypatch.setattr(api, 'voice_asset_ready', lambda _root: True)
    monkeypatch.setattr(api, 'voice_status', lambda _root: {'phase': 'ready', 'message': 'Installed.'})
    def fail(_root):
        raise VoicePlaybackError('audio_session_unavailable')
    monkeypatch.setattr(api, 'play_voice_preview', fail)
    with TestClient(create_app(data_dir=tmp_path)) as client:
        response = client.post('/api/v1/voice/asset/preview')
        assert response.status_code == 409
        assert 'audio session' in response.json()['detail']
        assert client.get('/api/v1/voice/asset').json()['last_preview_error'] == 'audio_session_unavailable'


def test_preview_reuses_live_voice_worker_without_starting_second_model(monkeypatch, tmp_path):
    import luma.api as api
    monkeypatch.setattr(api, 'voice_asset_ready', lambda _root: True)
    monkeypatch.setattr(api, 'voice_status', lambda _root: {'phase': 'ready', 'message': 'Installed.'})
    monkeypatch.setattr(api, 'play_voice_preview', lambda _root: pytest.fail('second worker started'))
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.post('/api/v1/voice/heartbeat', json={}).json()['accepted']
        result = []
        thread = threading.Thread(target=lambda: result.append(client.post('/api/v1/voice/asset/preview')))
        thread.start()
        pending = None
        for _ in range(100):
            pending = client.get('/api/v1/voice/asset/preview/pending').json()['request_id']
            if pending:
                break
            time.sleep(.01)
        assert pending
        assert client.post('/api/v1/voice/asset/preview/result', json={
            'request_id': pending, 'route': 'luma_speaker', 'error': None,
        }).json() == {'accepted': True}
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert result[0].json() == {'played': True, 'route': 'luma_speaker'}
        assert client.get('/api/v1/voice/asset/preview/pending').json()['request_id'] is None


def test_live_preview_reports_worker_failure_separately_from_speaker(monkeypatch, tmp_path):
    import luma.api as api
    monkeypatch.setattr(api, 'voice_asset_ready', lambda _root: True)
    monkeypatch.setattr(api, 'voice_status', lambda _root: {'phase': 'ready', 'message': 'Installed.'})
    with TestClient(create_app(data_dir=tmp_path)) as client:
        client.post('/api/v1/voice/heartbeat', json={})
        result = []
        thread = threading.Thread(target=lambda: result.append(client.post('/api/v1/voice/asset/preview')))
        thread.start()
        pending = None
        for _ in range(100):
            pending = client.get('/api/v1/voice/asset/preview/pending').json()['request_id']
            if pending:
                break
            time.sleep(.01)
        assert pending
        assert client.post('/api/v1/voice/asset/preview/result', json={
            'request_id': pending, 'error': 'piper_start_failed',
        }).json() == {'accepted': True}
        thread.join(timeout=5)
        assert result[0].status_code == 409
        assert 'worker could not start' in result[0].json()['detail']
        status = client.get('/api/v1/voice/asset').json()
        assert status['last_preview_error'] == 'piper_start_failed'
        assert status['last_tone_error'] is None


def test_piper_start_failure_has_distinct_code(monkeypatch, tmp_path):
    import luma.voice_speech as speech
    monkeypatch.setattr(speech, 'pulse_playback_environment', lambda: {})
    speaker = OfflineSpeaker(tmp_path)
    monkeypatch.setattr(speaker, '_start', lambda: (_ for _ in ()).throw(OSError('missing runtime')))
    with pytest.raises(VoicePlaybackError, match='piper_start_failed'):
        speaker._piper('Hello.')


def test_speaker_tone_result_is_local_and_separate_from_speech(monkeypatch, tmp_path):
    import luma.api as api
    def fail():
        raise VoicePlaybackError('speaker_route_unavailable')
    monkeypatch.setattr(api, 'play_test_tone', fail)
    with TestClient(create_app(data_dir=tmp_path)) as client:
        response = client.post('/api/v1/voice/asset/tone')
        assert response.status_code == 409
        status = client.get('/api/v1/voice/asset').json()
        assert status['last_tone_error'] == 'speaker_route_unavailable'
        assert status['last_preview_error'] is None
        remote = TestClient(client.app, client=('192.168.1.7', 5000))
        assert remote.post('/api/v1/voice/asset/tone').status_code == 403
        monkeypatch.setattr(api, 'play_test_tone', lambda: 'system_speaker')
        assert client.post('/api/v1/voice/asset/tone').json() == {
            'sent': True, 'route': 'system_speaker'
        }
        assert client.get('/api/v1/voice/asset').json()['last_tone_error'] is None
        assert client.get('/api/v1/voice/asset').json()['last_tone_route'] == 'system_speaker'


def test_live_speaker_tone_uses_voice_agent_and_reports_its_actual_route(monkeypatch, tmp_path):
    import luma.api as api
    monkeypatch.setattr(api, 'play_test_tone', lambda: (_ for _ in ()).throw(
        AssertionError('API service must not play while voice agent is live')))
    with TestClient(create_app(data_dir=tmp_path)) as client:
        client.post('/api/v1/voice/heartbeat', json={})
        responses = []
        thread = threading.Thread(target=lambda: responses.append(client.post('/api/v1/voice/asset/tone')))
        thread.start()
        pending = None
        for _ in range(100):
            pending = client.get('/api/v1/voice/asset/tone/pending').json()['request_id']
            if pending:
                break
            time.sleep(.01)
        assert pending
        assert client.post('/api/v1/voice/asset/tone/result', json={
            'request_id': pending, 'route': 'system_speaker',
        }).json() == {'accepted': True}
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert responses[0].json() == {'sent': True, 'route': 'system_speaker'}
        assert client.get('/api/v1/voice/asset/tone/pending').json()['request_id'] is None
        assert client.get('/api/v1/voice/asset').json()['last_tone_route'] == 'system_speaker'
        remote = TestClient(client.app, client=('192.168.1.7', 5000))
        assert remote.get('/api/v1/voice/asset/tone/pending').status_code == 403
        assert remote.post('/api/v1/voice/asset/tone/result', json={
            'request_id': pending, 'route': 'luma_speaker',
        }).status_code == 403


def test_reply_engine_is_reported_without_speech_text(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        response = client.post('/api/v1/voice/output-report', json={
            'engine': 'fallback', 'error': 'speaker_route_unavailable',
        })
        assert response.json() == {'accepted': True}
        status = client.get('/api/v1/voice/asset').json()
        assert status['last_reply_engine'] == 'fallback'
        assert status['last_reply_error'] == 'speaker_route_unavailable'
        assert status['last_reply_route'] is None
        assert status['last_reply_at']
        assert client.post('/api/v1/voice/output-report', json={
            'engine': 'silent', 'error': 'fallback_playback_failed',
            'primary_error': 'piper_start_failed',
        }).status_code == 200
        failed = client.get('/api/v1/voice/asset').json()
        assert failed['last_reply_engine'] == 'silent'
        assert failed['last_reply_primary_error'] == 'piper_start_failed'
        assert client.post('/api/v1/voice/output-report', json={
            'engine': 'piper', 'route': 'system_speaker', 'error': None,
        }).status_code == 200
        assert client.get('/api/v1/voice/asset').json()['last_reply_route'] == 'system_speaker'
        assert client.post('/api/v1/voice/output-report', json={
            'engine': 'piper', 'error': None, 'text': 'private speech',
        }).status_code == 422
        remote = TestClient(client.app, client=('192.168.1.7', 5000))
        assert remote.get('/api/v1/voice/asset').status_code == 403


def test_piper_wav_decoder_accepts_only_expected_mono_format():
    pcm = struct.pack('<hhhh', 0, 1000, -1000, 0)
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(22050)
        output.writeframes(pcm)
    assert wav_to_pcm(buffer.getvalue()) == pcm
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(22050)
        output.writeframes(pcm)
    with pytest.raises(ValueError):
        wav_to_pcm(buffer.getvalue())


def test_fallback_decoder_accepts_espeak_streaming_header_with_zero_lengths():
    data = (b'RIFF' + b'\x00' * 4 + b'WAVE' + b'fmt ' + struct.pack('<IHHIIHH',
            16, 1, 1, 22050, 44100, 2, 16) + b'data' + b'\x00' * 4
            + struct.pack('<hhhh', 0, 1000, -1000, 0))
    assert fallback_wav_to_pcm(data) == (struct.pack('<hhhh', 0, 1000, -1000, 0), 22050)
    with pytest.raises(ValueError):
        fallback_wav_to_pcm(data[:-1])


def test_failed_fallback_marks_reply_silent_instead_of_stale(monkeypatch, tmp_path):
    import luma.voice_speech as speech
    monkeypatch.setattr(speech, 'sys', SimpleNamespace(platform='linux'))
    monkeypatch.setattr(speech, 'ready', lambda _root: True)
    speaker = OfflineSpeaker(tmp_path)
    monkeypatch.setattr(speaker, '_piper', lambda _reply: (_ for _ in ()).throw(
        VoicePlaybackError('piper_start_failed')))
    monkeypatch.setattr(speech.subprocess, 'run', lambda *_args, **_kwargs: (_ for _ in ()).throw(
        OSError('fallback unavailable')))
    with pytest.raises(VoicePlaybackError, match='fallback_playback_failed'):
        speaker.speak('Hello.')
    assert speaker.last_error == 'fallback_playback_failed'
    assert speaker.last_primary_error == 'piper_start_failed'
    assert speaker.last_route is None


def test_install_keeps_settings_and_switches_only_after_smoke(tmp_path, monkeypatch):
    import luma.voice_asset as module
    monkeypatch.setattr(module, '_runtime_supported', lambda: True)
    package, public = make_asset(tmp_path)
    data = tmp_path / 'data'
    data.mkdir()
    settings = data / 'luma.db'
    settings.write_bytes(b'owner settings')
    calls = []
    def fake_run(command, **_kwargs):
        calls.append(command)
        if command[1:3] == ['-m', 'venv']:
            python = Path(command[3]) / 'bin/python'
            python.parent.mkdir(parents=True)
            python.write_bytes(b'python')
        if '-c' in command and str(data / 'voice-assets' / VOICE_ID) in command[0]:
            assert not ready(data / 'voice-assets')
    root = data / 'voice-assets'
    assert install_asset(package, root=root, public_key=public, run=fake_run)['phase'] == 'ready'
    assert ready(root) and settings.read_bytes() == b'owner settings'
    assert (root / VOICE_ID / 'sources/piper_tts-1.8.0.tar.gz').is_file()
    assert len(calls) == 4
    assert calls[-1][0] == str(root / VOICE_ID / 'venv/bin/python')
    assert not list(root.glob('.voice-stage-*'))


def test_failed_smoke_leaves_previous_settings_and_no_partial_voice(tmp_path, monkeypatch):
    import luma.voice_asset as module
    monkeypatch.setattr(module, '_runtime_supported', lambda: True)
    package, public = make_asset(tmp_path)
    data = tmp_path / 'data'
    data.mkdir()
    settings = data / 'luma.db'
    settings.write_bytes(b'owner settings')
    def fake_run(command, **_kwargs):
        if command[1:3] == ['-m', 'venv']:
            python = Path(command[3]) / 'bin/python'
            python.parent.mkdir(parents=True)
            python.write_bytes(b'python')
        if '-c' in command:
            raise subprocess.CalledProcessError(1, command)
    root = data / 'voice-assets'
    with pytest.raises(VoiceAssetError, match='fallback'):
        install_asset(package, root=root, public_key=public, run=fake_run)
    assert settings.read_bytes() == b'owner settings'
    assert not ready(root) and not (root / VOICE_ID).exists()
    assert not list(root.glob('.voice-stage-*'))


def test_post_rename_smoke_failure_removes_only_new_voice_files(tmp_path, monkeypatch):
    import luma.voice_asset as module
    monkeypatch.setattr(module, '_runtime_supported', lambda: True)
    package, public = make_asset(tmp_path)
    data = tmp_path / 'data'
    data.mkdir()
    settings = data / 'luma.db'
    settings.write_bytes(b'owner settings')
    root = data / 'voice-assets'
    def fake_run(command, **_kwargs):
        if command[1:3] == ['-m', 'venv']:
            python = Path(command[3]) / 'bin/python'
            python.parent.mkdir(parents=True)
            python.write_bytes(b'python')
        if '-c' in command and str(root / VOICE_ID) in command[0]:
            raise subprocess.CalledProcessError(1, command)
    with pytest.raises(VoiceAssetError, match='fallback'):
        install_asset(package, root=root, public_key=public, run=fake_run)
    assert settings.read_bytes() == b'owner settings'
    assert not ready(root) and not (root / VOICE_ID).exists()
    assert not list(root.glob('.voice-stage-*'))


def _fake_voice_install_run(command, **_kwargs):
    if command[1:3] == ['-m', 'venv']:
        python = Path(command[3]) / 'bin/python'
        python.parent.mkdir(parents=True)
        python.write_bytes(b'python')


def test_signed_repair_replaces_only_voice_and_keeps_settings(tmp_path, monkeypatch):
    import luma.voice_asset as module
    monkeypatch.setattr(module, '_runtime_supported', lambda: True)
    package, public = make_asset(tmp_path)
    root = tmp_path / 'data' / 'voice-assets'
    root.mkdir(parents=True)
    settings = root.parent / 'luma.db'
    settings.write_bytes(b'owner settings')
    old = root / VOICE_ID
    (old / 'venv/bin').mkdir(parents=True)
    (old / MODEL).parent.mkdir(parents=True)
    (old / MODEL).write_bytes(b'old model')
    (old / CONFIG).write_bytes(b'{}')
    (old / 'venv/bin/python').write_bytes(b'old python')
    assert ready(root)
    assert install_asset(package, root=root, public_key=public, run=_fake_voice_install_run,
                         replace_existing=True)['phase'] == 'ready'
    assert (old / MODEL).read_bytes() == b'model-bytes'
    assert not (root / PREVIOUS_VOICE).exists()
    assert settings.read_bytes() == b'owner settings'


def test_failed_signed_repair_restores_previous_voice(tmp_path, monkeypatch):
    import luma.voice_asset as module
    monkeypatch.setattr(module, '_runtime_supported', lambda: True)
    package, public = make_asset(tmp_path)
    root = tmp_path / 'voice-assets'
    old = root / VOICE_ID
    (old / 'venv/bin').mkdir(parents=True)
    (old / MODEL).parent.mkdir(parents=True)
    (old / MODEL).write_bytes(b'old model')
    (old / CONFIG).write_bytes(b'{}')
    (old / 'venv/bin/python').write_bytes(b'old python')
    def fail_final_run(command, **kwargs):
        _fake_voice_install_run(command, **kwargs)
        if '-c' in command and command[0] == str(old / 'venv/bin/python'):
            raise subprocess.CalledProcessError(1, command)
    with pytest.raises(VoiceAssetError, match='fallback'):
        install_asset(package, root=root, public_key=public, run=fail_final_run,
                      replace_existing=True)
    assert ready(root)
    assert (old / MODEL).read_bytes() == b'old model'
    assert not (root / PREVIOUS_VOICE).exists()


def test_failed_download_keeps_old_voice_but_exposes_repair_error(tmp_path):
    root = tmp_path / 'voice-assets'
    old = root / VOICE_ID
    (old / 'venv/bin').mkdir(parents=True)
    (old / MODEL).parent.mkdir(parents=True)
    (old / MODEL).write_bytes(b'old model')
    (old / CONFIG).write_bytes(b'{}')
    (old / 'venv/bin/python').write_bytes(b'old python')
    write_status(root, 'failed', 'The signed download could not be verified.')
    status = voice_status(root)
    assert status['phase'] == 'ready'
    assert status['repair_error'] == 'The signed download could not be verified.'
    assert ready(root)


def test_power_loss_during_repair_recovers_previous_voice(tmp_path):
    root = tmp_path / 'voice-assets'
    root.mkdir()
    previous = root / PREVIOUS_VOICE
    previous.mkdir()
    (previous / 'marker').write_bytes(b'previous voice')
    final = root / VOICE_ID
    final.mkdir()
    (final / 'marker').write_bytes(b'unverified voice')
    write_status(root, 'installing', 'Installing the verified offline voice.')
    assert recover_interrupted_repair(root)
    assert (final / 'marker').read_bytes() == b'previous voice'
    assert not previous.exists()
    assert voice_status(root)['phase'] == 'failed'  # Fixture lacks model/runtime files.


def test_voice_repair_endpoint_needs_installed_voice_and_local_pi(monkeypatch, tmp_path):
    import luma.api as api
    monkeypatch.setattr(api, 'voice_asset_ready', lambda _root: True)
    monkeypatch.setattr(api, 'voice_status', lambda _root: {'phase': 'ready', 'message': 'Installed.'})
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.post('/api/v1/voice/asset/repair').status_code == 409
        remote = TestClient(client.app, client=('192.168.1.7', 5000))
        assert remote.post('/api/v1/voice/asset/repair').status_code == 403


class FakeResponse:
    def __init__(self, url, body):
        self.url, self.body, self.position = url, body, 0
        self.headers = {'Content-Length': str(len(body))}
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def geturl(self):
        return self.url
    def read(self, length=-1):
        end = len(self.body) if length < 0 else min(len(self.body), self.position + length)
        block = self.body[self.position:end]
        self.position = end
        return block


def test_voice_download_accepts_exact_stable_release_then_calls_signed_installer(tmp_path):
    package, public = make_asset(tmp_path)
    body = package.read_bytes()
    url = f'https://github.com/BrianBGoldshtein/LumaSmartHub/releases/download/v0.2.4/{VOICE_ASSET_NAME}'
    release = {'draft': False, 'prerelease': False, 'target_commitish': 'main',
               'tag_name': 'v0.2.4', 'assets': [{'name': VOICE_ASSET_NAME,
               'size': len(body), 'digest': 'sha256:' + hashlib.sha256(body).hexdigest(),
               'browser_download_url': url}]}
    class Opener:
        def open(self, request, timeout):
            return FakeResponse(request.full_url,
                                json.dumps(release).encode() if request.full_url == VOICE_RELEASE_URL else body)
    calls = []
    def installer(path, *, root, public_key):
        calls.append((path.read_bytes(), root, public_key))
        return {'phase': 'ready'}
    root = tmp_path / 'voice-assets'
    assert fetch_and_install(root=root, public_key=public, opener=Opener(), installer=installer) == {'phase': 'ready'}
    assert calls == [(body, root, public)]
    assert not list(root.glob('.voice-download-*.lva'))


def test_voice_repair_fetches_signed_asset_even_when_old_files_exist(tmp_path):
    package, public = make_asset(tmp_path)
    body = package.read_bytes()
    url = f'https://github.com/BrianBGoldshtein/LumaSmartHub/releases/download/v0.2.4/{VOICE_ASSET_NAME}'
    release = {'draft': False, 'prerelease': False, 'target_commitish': 'main',
               'tag_name': 'v0.2.4', 'assets': [{'name': VOICE_ASSET_NAME,
               'size': len(body), 'digest': 'sha256:' + hashlib.sha256(body).hexdigest(),
               'browser_download_url': url}]}
    class Opener:
        def open(self, request, timeout):
            return FakeResponse(request.full_url,
                                json.dumps(release).encode() if request.full_url == VOICE_RELEASE_URL else body)
    root = tmp_path / 'voice-assets'
    old = root / VOICE_ID
    (old / 'venv/bin').mkdir(parents=True)
    (old / MODEL).parent.mkdir(parents=True)
    (old / MODEL).write_bytes(b'old model')
    (old / CONFIG).write_bytes(b'{}')
    (old / 'venv/bin/python').write_bytes(b'old python')
    calls = []
    def installer(path, *, root, public_key, replace_existing):
        calls.append((path.read_bytes(), replace_existing))
        return {'phase': 'ready'}
    assert fetch_and_install(root=root, public_key=public, opener=Opener(),
                             installer=installer, replace_existing=True)['phase'] == 'ready'
    assert calls == [(body, True)]
    assert (old / MODEL).read_bytes() == b'old model'


def test_voice_download_rejects_wrong_published_checksum_before_install(tmp_path):
    package, public = make_asset(tmp_path)
    body = package.read_bytes()
    url = f'https://github.com/BrianBGoldshtein/LumaSmartHub/releases/download/v0.2.4/{VOICE_ASSET_NAME}'
    release = {'draft': False, 'prerelease': False, 'target_commitish': 'main',
               'tag_name': 'v0.2.4', 'assets': [{'name': VOICE_ASSET_NAME,
               'size': len(body), 'digest': 'sha256:' + '0'*64,
               'browser_download_url': url}]}
    class Opener:
        def open(self, request, timeout):
            return FakeResponse(request.full_url,
                                json.dumps(release).encode() if request.full_url == VOICE_RELEASE_URL else body)
    root = tmp_path / 'voice-assets'
    with pytest.raises(VoiceAssetError, match='checksum'):
        fetch_and_install(root=root, public_key=public, opener=Opener(), installer=lambda *_a, **_k: pytest.fail())
    assert voice_status(root)['phase'] == 'failed'
