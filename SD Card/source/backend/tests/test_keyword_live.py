from array import array
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from luma.api import create_app
from luma import keyword_live
from luma.keyword_live import LiveKeywordRuntime
from luma.keyword_wake import KeywordWakeError, KeywordEvidence
from luma.voice_calibration import VoiceCalibration
from luma.voice_call_trial import VoiceCallTrial
from luma.voice_agent import calibration_decoding_payload, call_trial_decoding_payload
from luma.voice_signal import AudioProfile


@pytest.mark.parametrize('saved,expected', [
    (None,'acoustic'), ({'version':1,'mode':'standard'},'acoustic'),
    ({'version':2,'mode':'dual_decoder'},'acoustic'),
    ({'version':2,'mode':'standard'},'standard'),
    ({'version':3,'mode':'dual_decoder'},'dual_decoder'),
    ({'version':3,'mode':'standard'},'standard'),
    ({'version':3,'mode':'acoustic'},'acoustic'),
    ({'version':3.0,'mode':'standard'},'acoustic'),
])
def test_production_default_migration_preserves_sensitive_consent_and_other_saved_state(tmp_path,saved,expected):
    app = create_app(data_dir=tmp_path)
    storage = app.state.luma.storage
    if saved is not None: storage.set_cache('voice','wake_confirmation',saved)
    storage.set_cache('preservation-probe','token',{'sentinel':'not-an-account'})
    client = TestClient(app)
    result = client.get('/api/v1/voice/calibration').json()
    assert result['wake_confirmation'] == {'version':3,'mode':expected}
    assert not result['strict_wake_ready']
    assert storage.get_cache('preservation-probe','token') == {'sentinel':'not-an-account'}
    if expected == 'acoustic':
        assert client.post('/api/v1/voice/calibration/start').status_code == 409
        assert not result['keyword_asset_available']
    assert client.post('/api/v1/voice/wake-confirmation',json={'mode':'dual_decoder'}).status_code == 200
    assert storage.get_cache('voice','wake_confirmation') == {'version':3,'mode':'dual_decoder'}
    assert TestClient(create_app(data_dir=tmp_path)).get('/api/v1/voice/calibration').json()['wake_confirmation'] == {
        'version':3,'mode':'dual_decoder'}


@pytest.mark.parametrize('detected,ready,dropped,expected,api_available', [
    (True,True,False,True,True), (False,True,False,False,True),
    (True,False,False,False,True), (True,True,True,False,True),
    (True,False,False,False,False),
])
def test_actual_main_loop_uses_acoustic_evidence_without_a_name_proposal_and_checks_capture_gap(
        tmp_path, monkeypatch, detected, ready, dropped, expected, api_available):
    import sys
    import queue
    import luma.voice_agent as agent
    (tmp_path/'am').mkdir()
    monkeypatch.setenv('LUMA_VOSK_MODEL',str(tmp_path))
    monkeypatch.setattr(agent.signal,'signal',Mock())
    monkeypatch.setattr(agent.atexit,'register',Mock())
    monkeypatch.setattr(agent,'StatusLeds',Mock())
    monkeypatch.setattr(agent,'OfflineSpeaker',Mock())
    monkeypatch.setattr(agent,'accept_live_utterance',Mock(side_effect=AssertionError('No sensitivity fallback')))
    pcm = array('h',[1000]*4000).tobytes()
    class ScriptQueue:
        def __init__(self,*args,**kwargs): self.index = 0
        def empty(self): return True
        def get_nowait(self): raise queue.Empty
        def get(self,**kwargs):
            self.index += 1
            return pcm if self.index <= 12 else agent.AudioCaptureError('capture_stream_stopped')
    monkeypatch.setattr(agent.queue,'Queue',ScriptQueue)
    capture = SimpleNamespace(dropped_frames=0,stalled=lambda:False)
    context = Mock()
    context.__enter__ = Mock(return_value=capture)
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(agent,'PulseCapture',Mock(return_value=context))
    class Decoder:
        def __init__(self,*args): self.index = 0
        def Reset(self): self.index = 0
        def SetWords(self,value): pass
        def AcceptWaveform(self,chunk):
            self.index += 1
            return self.index == 12
        def Result(self):
            words = [('hey',.1,.3),('lunar',.3,.7),('what',.72,.9),('time',.9,1.1),('is',1.1,1.2),('it',1.2,1.3)]
            return json.dumps({'text':'hey lunar what time is it','result':[
                {'word':word,'start':start,'end':end} for word,start,end in words]})
        def FinalResult(self): return '{}'
    monkeypatch.setitem(sys.modules,'vosk',SimpleNamespace(Model=Mock(),KaldiRecognizer=Decoder,SetLogLevel=Mock()))
    verifier = Mock()
    def verify(frames):
        if dropped: capture.dropped_frames += 1
        return KeywordEvidence(detected,.1 if detected else None,.6 if detected else None)
    verifier.verify.side_effect = verify
    live = Mock(phase='ready' if ready else 'waiting_asset',verifier=verifier)
    live.synchronize.side_effect = lambda *args,**kwargs: False
    live.public.return_value = {'mode':'acoustic','phase':live.phase,'error':None}
    monkeypatch.setattr(agent,'LiveKeywordRuntime',Mock(return_value=live))
    requests = []
    client = Mock()
    def get(path):
        if not api_available and path.endswith('/calibration'):
            raise agent.httpx.RequestError('Local API temporarily unavailable')
        body = {'active':False,'session':'','wake_confirmation':{'version':3,'mode':'acoustic'},
                'call_trial':{'active':False},'speaker_trial':{'active':False}}
        return SimpleNamespace(json=lambda:body if path.endswith('/calibration') else {},raise_for_status=lambda:None)
    def post(path,**kwargs):
        requests.append((path,kwargs.get('json')))
        return SimpleNamespace(json=lambda:{'message':'It is noon.','speak':False},raise_for_status=lambda:None)
    client.get.side_effect = get; client.post.side_effect = post
    client.__enter__ = Mock(return_value=client); client.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(agent.httpx,'Client',Mock(return_value=client))
    with pytest.raises(SystemExit): agent.main()
    commands = [payload for path,payload in requests if path.endswith('/voice/command')]
    assert commands == ([{'text':'what time is it'}] if expected else [])
    listening = [payload for path,payload in requests if path.endswith('/voice/phase') and payload['phase']=='listening']
    assert bool(listening) == expected
    agent.accept_live_utterance.assert_not_called()
    assert all(call.args[0] == 'acoustic' for call in live.synchronize.call_args_list)
    if not ready: verifier.verify.assert_not_called()


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(keyword_live.keyword_asset, 'ready', Mock(return_value=True))
    verifier = Mock()
    verifier.prepare.side_effect = [True, False, False]
    monkeypatch.setattr(keyword_live, 'IsolatedKeywordVerifier', Mock(return_value=verifier))
    return LiveKeywordRuntime(tmp_path), verifier


def test_only_signed_installer_paths_are_used_and_warmup_requires_a_reset(runtime):
    live, verifier = runtime
    assert live.synchronize('acoustic')
    folder = live.root / keyword_live.keyword_asset.KEYWORD_ID
    keyword_live.IsolatedKeywordVerifier.assert_called_once_with(folder/'venv/bin/python', folder/'model')
    assert live.public('acoustic') == {'mode':'acoustic','phase':'ready','error':None}
    assert not live.synchronize('acoustic')
    assert verifier.prepare.call_count == 2


@pytest.mark.parametrize('conditions,phase', [({'installing':True},'preparing_asset'),
                                            ({'suspended':True},'suspended')])
def test_repair_and_speaker_trial_close_native_model_and_require_new_capture_boundary(runtime, conditions, phase):
    live, verifier = runtime
    live.synchronize('acoustic')
    assert live.synchronize('acoustic', **conditions)
    verifier.close.assert_called_once()
    assert live.verifier is None and live.phase == phase
    assert not live.synchronize('acoustic', **conditions)
    assert live.synchronize('acoustic')


def test_missing_asset_never_starts_or_falls_back_to_sensitive_wake(runtime):
    live, verifier = runtime
    keyword_live.keyword_asset.ready.return_value = False
    assert live.synchronize('acoustic')
    assert live.phase == 'waiting_asset'
    keyword_live.IsolatedKeywordVerifier.assert_not_called()
    verifier.prepare.assert_not_called()
    assert not live.synchronize('acoustic')


def test_switching_to_legacy_closes_worker_and_failure_backoff_cannot_look_ready(runtime):
    live, verifier = runtime
    live.synchronize('acoustic')
    live.report_error('keyword_decode_timeout')
    verifier.prepare.side_effect = KeywordWakeError('keyword_retry_wait')
    assert not live.synchronize('acoustic')  # already failed; no new capture boundary
    assert live.public('acoustic') == {'mode':'acoustic','phase':'failed','error':'keyword_retry_wait'}
    assert live.synchronize('dual_decoder')
    verifier.close.assert_called_once()
    assert live.phase == 'inactive' and live.verifier is None


def test_rejected_quoted_speech_is_not_a_model_failure(runtime):
    live, _ = runtime
    live.synchronize('acoustic')
    live.report_error('keyword_prefix_rejected')
    assert live.phase == 'ready' and live.error is None


def test_acoustic_selection_is_local_persistent_and_model_install_does_not_select_it(tmp_path):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    endpoint = '/api/v1/voice/wake-confirmation'
    remote = TestClient(app, client=('192.168.1.7',5000))
    assert remote.post(endpoint,json={'mode':'acoustic'}).status_code == 403
    assert client.post(endpoint,json={'mode':'acoustic','model_directory':'/secret'}).status_code == 422
    assert client.post(endpoint,json={'mode':'acoustic'}).json() == {
        'wake_confirmation':{'version':3,'mode':'acoustic'}}
    assert app.state.luma.storage.get_cache('voice','wake_confirmation') == {'version':3,'mode':'acoustic'}
    status = client.get('/api/v1/voice/calibration').json()
    assert status['wake_confirmation'] == {'version':3,'mode':'acoustic'}
    assert not status['keyword_asset_available'] and status['wake_detector'] is None


def test_detector_heartbeat_is_typed_ephemeral_and_not_install_or_owner_readiness(tmp_path):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    endpoint = '/api/v1/voice/heartbeat'
    status = {'mode':'acoustic','phase':'waiting_asset','error':'keyword_model_unavailable'}
    assert client.post(endpoint,json={'wake_detector':status}).status_code == 200
    report = client.get('/api/v1/voice/calibration').json()
    assert report['wake_detector'] == status and report['agent_available']
    assert not report['strict_wake_ready']
    assert client.post(endpoint,json={'wake_detector':{**status,'error':'secret /path'}}).status_code == 422
    assert create_app(data_dir=tmp_path).state.luma.storage.get_cache('voice','wake_detector') is None


def test_checks_wait_for_selected_phonetic_listener_and_samples_must_use_that_detector(tmp_path, monkeypatch):
    import luma.api as api
    original = api.VoiceCalibration.start
    monkeypatch.setattr(api.VoiceCalibration,'start',lambda self,**kwargs:original(self))
    client = TestClient(create_app(data_dir=tmp_path))
    client.post('/api/v1/voice/wake-confirmation',json={'mode':'acoustic'})
    assert client.post('/api/v1/voice/calibration/start').status_code == 409
    assert client.post('/api/v1/voice/call-trial/start').status_code == 409
    client.post('/api/v1/voice/heartbeat',json={'wake_detector':{'mode':'acoustic','phase':'ready','error':None}})
    started = client.post('/api/v1/voice/calibration/start')
    assert started.status_code == 200
    body = {'session':started.json()['session'],'text':'hey luma set brightness to fifty',
            'free_text':'hey lunar set brightness to fifty','rms':.05,'peak':.4,
            'selected_text':'set brightness to fifty','selection':'constrained'}
    assert client.post('/api/v1/voice/calibration/sample',json=body).status_code == 409
    denied = client.post('/api/v1/voice/calibration/sample',json={**body,'acoustic_wake':False})
    assert denied.status_code == 200 and denied.json()['completed'] == 0
    accepted = client.post('/api/v1/voice/calibration/sample',json={**body,'acoustic_wake':True,
        'acoustic_free_text':'hey luma set brightness to fifty'})
    assert accepted.status_code == 200 and accepted.json()['completed'] == 1
    assert client.post('/api/v1/voice/wake-confirmation',json={'mode':'standard'}).status_code == 409
    client.post('/api/v1/voice/calibration/cancel')
    changed = client.post('/api/v1/voice/wake-confirmation',json={'mode':'standard'})
    assert changed.status_code == 200
    assert not client.get('/api/v1/voice/calibration').json()['strict_wake_ready']


def test_calibration_cannot_substitute_grammar_spelling_for_failed_acoustic_evidence():
    check = VoiceCalibration(); session = check.start(now=100)['session']
    result = check.submit(session,'hey luma set brightness to fifty',.05,.4,now=101,
        free_text='hey luma set brightness to fifty',acoustic_wake=False)
    assert result['completed'] == 0 and not result['last_wake_detected']
    result = check.submit(session,'hey lunar set brightness to fifty',.05,.4,now=102,
        free_text='hey lunar set brightness to fifty',acoustic_wake=True,
        acoustic_free_text='hey luma set brightness to fifty',selected_text='set brightness to fifty',
        selection='agree')
    assert result['completed'] == 1 and result['last_wake_detected']
    assert result['last_heard'] == 'hey lunar set brightness to fifty'
    assert result['results'][1]['acoustic_wake'] is True


def test_call_trial_cannot_claim_acoustic_negative_readiness_from_legacy_counts():
    def measured(acoustic):
        trial = VoiceCallTrial(); session = trial.start(now=100)['session']; trial.arm(session,now=101)
        for now in range(106,191,5):
            trial.heartbeat(now)
            trial.record(session,partial_wake=False,constrained_wake=False,
                constrained_near_start=False,free_wake=False,free_near_start=False,
                acoustic_wake=acoustic,now=now)
        return trial.status(now=192)
    assert measured(None)['negative_ready']
    assert not measured(None)['acoustic_negative_ready']
    assert measured(False)['acoustic_negative_ready']
    assert not measured(True)['acoustic_negative_ready']
