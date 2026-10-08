import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
from time import monotonic
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from luma.api import create_app
from luma import piper_worker as worker
from luma import voice_speech as speech
from luma.voice_agent import present_voice_response


def chunk(pcm=b'\x01\x00' * 40, **kwargs):
    return SimpleNamespace(audio_int16_bytes=pcm, sample_rate=22050,
                           sample_width=2, sample_channels=1, **kwargs)


def test_worker_sends_first_sentence_before_generating_the_next():
    output = io.BytesIO()
    def synthesize(text):
        yield chunk()
        assert output.getvalue() == struct.pack('>I', 80) + chunk().audio_int16_bytes
        yield chunk()
    worker.stream_audio(SimpleNamespace(synthesize=synthesize), 'First. Second.', output)
    assert output.getvalue() == (struct.pack('>I', 80) + chunk().audio_int16_bytes) * 2 + bytes(4)


@pytest.mark.parametrize('bad', [[], [chunk(b'')], [chunk(b'x')],
                               [SimpleNamespace(audio_int16_bytes=b'xx', sample_rate=48000,
                                                sample_width=2, sample_channels=1)]])
def test_worker_rejects_empty_or_wrong_pcm_with_fixed_protocol_error(bad):
    output = io.BytesIO()
    worker.stream_audio(SimpleNamespace(synthesize=lambda text: iter(bad)), 'Hi.', output)
    assert output.getvalue() == struct.pack('>I', worker.STREAM_ERROR)


@pytest.mark.parametrize('size,code', [(0,'piper_audio_invalid'), (1,'piper_audio_invalid'),
                                    (16386,'piper_audio_invalid'), (0xffffffff,'piper_synthesis_failed')])
def test_reader_rejects_invalid_stream_without_allocating_declared_size(monkeypatch, size, code):
    read = Mock(return_value=struct.pack('>I', size))
    monkeypatch.setattr(speech, '_read_exact', read)
    with pytest.raises(speech.VoicePlaybackError, match=code):
        list(speech._stream_frames(None, monotonic() + 1))
    read.assert_called_once()


def test_prepare_loads_once_without_synthesis_or_speaker(monkeypatch, tmp_path):
    monkeypatch.setattr(speech, 'ready', lambda root: True)
    speaker = speech.OfflineSpeaker(tmp_path)
    process = Mock()
    process.poll.return_value = None
    def start():
        speaker.process = process
        return process
    started = Mock(side_effect=start)
    monkeypatch.setattr(speaker, '_start', started)
    assert speaker.prepare() and speaker.prepare()
    started.assert_called_once()


def test_failed_prepare_has_bounded_retry_and_does_not_attempt_audio(monkeypatch, tmp_path):
    monkeypatch.setattr(speech, 'ready', lambda root: True)
    speaker = speech.OfflineSpeaker(tmp_path)
    started = Mock(side_effect=speech.VoicePlaybackError('piper_start_timeout'))
    monkeypatch.setattr(speaker, '_start', started)
    assert not speaker.prepare() and not speaker.prepare()
    started.assert_called_once()
    assert speaker.failure_cause == 'piper_start_timeout'


def test_partially_played_neural_reply_never_repeats_using_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(speech, 'ready', lambda root: True)
    speaker = speech.OfflineSpeaker(tmp_path)
    def fail(text):
        speaker.last_playback_started = True
        raise speech.VoicePlaybackError('speaker_playback_failed')
    monkeypatch.setattr(speaker, '_piper', fail)
    fallback = Mock()
    monkeypatch.setattr(speaker, '_fallback', fallback)
    with pytest.raises(speech.VoicePlaybackError):
        speaker.speak('Hi.')
    fallback.assert_not_called()


def test_speaking_phase_starts_on_submission_not_before_generation(monkeypatch, tmp_path):
    speaker = speech.OfflineSpeaker(tmp_path)
    phases = []
    speaker.on_playback_started = lambda: phases.append('speaking')
    def say(text):
        assert phases == ['thinking']
        speaker._started()
        return 'piper'
    present_voice_response({'message': 'Hi.'}, say=say, phase=phases.append)
    assert phases == ['thinking', 'speaking']


def test_long_fallback_pcm_is_submitted_in_bounded_frames(monkeypatch):
    def play(frames, env, started, *, rate):
        frames = list(frames)
        assert max(map(len,frames)) <= 16384
        assert b''.join(frames) == b'\x01\x00'*100000
        assert rate == 16000
        started()
        return 'system_speaker'
    monkeypatch.setattr(speech, '_play_pcm_stream', play)
    started = Mock()
    assert speech._play_pcm(b'\x01\x00'*100000, {}, rate=16000, on_started=started) == 'system_speaker'
    started.assert_called_once()


def test_partial_first_frame_marks_submission_before_later_pipe_failure(monkeypatch):
    process = SimpleNamespace(stdin=SimpleNamespace(fileno=lambda:42))
    monkeypatch.setattr(speech.os,'set_blocking',Mock())
    monkeypatch.setattr(speech.select,'select',lambda *args: ([],[42],[]))
    monkeypatch.setattr(speech.os,'write',Mock(side_effect=[2,BrokenPipeError()]))
    submitted = Mock()
    with pytest.raises(BrokenPipeError):
        speech._write_pcm(process,b'\x01\x00'*20,monotonic()+1,on_first_write=submitted)
    submitted.assert_called_once()


def test_numeric_output_timing_is_local_bounded_and_not_saved_with_words(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        body = {'engine': 'piper', 'route': 'system_speaker',
                'timings': {'model_start_ms': 1, 'route_setup_ms': 2,
                            'first_pcm_ms': 300, 'playback_submit_ms': 320, 'output_total_ms': 1200}}
        assert client.post('/api/v1/voice/output-report', json=body).status_code == 200
        status = client.get('/api/v1/voice/asset').json()
        assert status['last_reply_timings'] == body['timings']
        assert all('timings' not in row for row in status['health_history'])
        for bad in ({'text':'PRIVATE'}, {'first_pcm_ms':-1}, {'first_pcm_ms':600001}):
            assert client.post('/api/v1/voice/output-report', json={**body, 'timings':bad}).status_code == 422


@pytest.mark.skipif(sys.platform != 'linux', reason='uses real Linux pipe and player processes')
def test_real_worker_pipes_play_first_pcm_before_remaining_sentence(monkeypatch, tmp_path):
    """Not a real model/speaker test; verifies the actual streaming transport."""
    release = tmp_path / 'submitted'
    output = tmp_path / 'pcm'
    program = '''
import sys,time,pathlib
from types import SimpleNamespace
from luma import piper_worker as w
release=pathlib.Path(sys.argv[1])
class Voice:
    def synthesize(self,text):
        yield SimpleNamespace(audio_int16_bytes=b'\\x01\\x00'*80,sample_rate=22050,sample_width=2,sample_channels=1)
        if text!='Ready.':
            end=time.monotonic()+5
            while not release.exists():
                if time.monotonic()>end: raise RuntimeError('playback was not early')
                time.sleep(.01)
            yield SimpleNamespace(audio_int16_bytes=b'\\x02\\x00'*80,sample_rate=22050,sample_width=2,sample_channels=1)
w.load_voice=lambda path:Voice()
sys.argv=['piper_worker.py','model']
# The normal import guard still checks that the dependency is present.
sys.modules['piper']=SimpleNamespace(PiperVoice=Voice)
w.main()
'''
    real_popen = subprocess.Popen
    env = {**os.environ, 'PYTHONPATH': str(Path(worker.__file__).resolve().parents[1])}
    producer = real_popen([sys.executable,'-c',program,str(release)], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, bufsize=0)
    def player(command, **kwargs):
        assert command[0] == 'pacat' and '--device=alsa_output.test' in command
        return real_popen([sys.executable,'-c',
                          'import sys,pathlib;pathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())',
                          str(output)], **kwargs)
    monkeypatch.setattr(speech.subprocess,'Popen',player)
    monkeypatch.setattr(speech,'_speaker_routes',lambda env:['alsa_output.test'])
    try:
        assert speech._read_exact(producer,6,monotonic()+5) == b'READY\n'
        producer.stdin.write(json.dumps({'text':'First. Second.','stream':True}).encode()+b'\n')
        producer.stdin.flush()
        route = speech._play_pcm_stream(speech._stream_frames(producer,monotonic()+5), {},
                                       lambda:release.touch())
        assert route == 'system_speaker'
        assert output.read_bytes() == b'\x01\x00'*80 + b'\x02\x00'*80
        # A second request on the same worker verifies that stream termination
        # leaves no bytes to corrupt the following command.
        producer.stdin.write(json.dumps({'text':'Again.','stream':True}).encode()+b'\n')
        producer.stdin.flush()
        assert list(speech._stream_frames(producer,monotonic()+5)) == [b'\x01\x00'*80,b'\x02\x00'*80]
    finally:
        producer.kill()
        producer.wait(timeout=5)
        for pipe in (producer.stdin,producer.stdout,producer.stderr):
            pipe.close()


def test_model_thread_budget_is_explicit_and_uses_pinned_piper_configuration(monkeypatch, tmp_path):
    model = tmp_path/'kristin.onnx'
    Path(str(model)+'.json').write_text('{}')
    options = SimpleNamespace(add_session_config_entry=Mock())
    session = Mock()
    config = Mock()
    voice = Mock()
    monkeypatch.setitem(sys.modules,'onnxruntime',SimpleNamespace(SessionOptions=lambda:options,InferenceSession=session))
    monkeypatch.setitem(sys.modules,'piper',SimpleNamespace(PiperVoice=voice))
    monkeypatch.setitem(sys.modules,'piper.config',SimpleNamespace(PiperConfig=SimpleNamespace(from_dict=config)))
    worker.load_voice(str(model))
    assert options.intra_op_num_threads == 2 and options.inter_op_num_threads == 1
    assert options.add_session_config_entry.call_count == 2
    assert session.call_args.kwargs['providers'] == ['CPUExecutionProvider']
    voice.assert_called_once_with(config=config.return_value, session=session.return_value)
