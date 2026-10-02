from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from luma.api import create_app
from luma.focus_timer import FocusTimer
from luma.storage import Storage
from luma.voice import parse_local_command, command_grammar
from luma.shortcut_protocol import parse_command
from luma.timer_chime import TimerChimeBridge, chime_pcm

NOW = datetime(2026,9,26,12,tzinfo=UTC)


@pytest.fixture
def timer(tmp_path):
    clock = Mock(return_value=100.)
    timer = FocusTimer(Storage(tmp_path/'luma.db'), clock=clock)
    timer.tick(NOW, trusted=True)
    return timer, clock


def test_pause_resume_monotonic_and_once_only_completion(timer):
    t,c = timer
    t.execute('start_timer',1,now=NOW)
    c.return_value = 120
    t.tick(NOW+timedelta(hours=3))  # wall-clock jump must not move live countdown.
    assert t.snapshot()['remaining_seconds']==40
    t.execute('pause_timer',now=NOW)
    c.return_value=500
    assert t.snapshot()['remaining_seconds']==40
    t.execute('resume_timer',now=NOW)
    c.return_value=540
    assert t.tick(NOW)
    assert t.snapshot()['status']=='complete'
    assert t.claim_chime() and not t.claim_chime()
    assert not t.tick(NOW)
    t.execute('dismiss_timer',now=NOW)
    assert t.snapshot()['status']=='idle'


def test_no_periodic_database_writes(timer):
    t,c=timer
    t.execute('start_timer',5,now=NOW)
    t.storage.set_cache=Mock(wraps=t.storage.set_cache)
    for second in range(1,120):
        c.return_value=100+second
        t.tick(NOW+timedelta(seconds=second))
        t.snapshot()
    t.storage.set_cache.assert_not_called()


def test_recovery_requires_time_trust_and_never_replays_sound(timer):
    t,c=timer
    t.execute('start_timer',1,now=NOW)
    recovered=FocusTimer(t.storage,clock=c)
    assert recovered.snapshot()['status']=='awaiting_time'
    assert not recovered.tick(NOW+timedelta(seconds=20),trusted=False)
    assert recovered.tick(NOW+timedelta(seconds=20),trusted=True)
    assert recovered.snapshot()['remaining_seconds']==40
    expired=FocusTimer(t.storage,clock=c)
    expired.tick(NOW+timedelta(minutes=2),trusted=True)
    assert expired.snapshot()['status']=='complete'
    assert not expired.claim_chime()
    assert not FocusTimer(t.storage,clock=c).claim_chime()


def test_untrusted_start_requires_manual_resume_after_reboot(timer):
    t,c=timer
    t.tick(NOW,trusted=False)
    t.execute('start_timer',1,now=NOW)
    recovered=FocusTimer(t.storage,clock=c)
    recovered.tick(NOW,trusted=True)
    assert recovered.snapshot()['status']=='paused'
    assert 'Clock changed' in recovered.snapshot()['note']
    assert recovered.execute('resume_timer',now=NOW).accepted


def test_clock_correction_reanchors_recovery_without_changing_live_time(timer):
    t,c=timer
    t.tick(NOW,trusted=False)
    t.execute('start_timer',5,now=NOW)
    c.return_value=120
    corrected=NOW+timedelta(days=1)
    t.tick(corrected,trusted=True)
    assert t.snapshot()['remaining_seconds']==280
    recovered=FocusTimer(t.storage,clock=c)
    recovered.tick(corrected+timedelta(seconds=10),trusted=True)
    assert recovered.snapshot()['remaining_seconds']==270


def test_replacement_requires_current_id_and_never_voice_overwrite(timer):
    t,c=timer
    t.execute('start_timer','focus',now=NOW,focus=30)
    first=t.snapshot()['id']
    assert not t.execute('start_timer',5,now=NOW).accepted
    assert not t.execute('start_timer',{'minutes':5,'replace_id':'stale'},now=NOW).accepted
    with pytest.raises(ValueError):
        t.execute('start_timer',{'minutes':5,'replace_id':first},now=NOW,source='voice')
    assert t.execute('start_timer',{'minutes':5,'replace_id':first},now=NOW).accepted
    assert t.snapshot()['id']!=first
    assert not t.execute('start_timer',{'minutes':1,'replace_id':first},now=NOW).accepted


@pytest.mark.parametrize('value',[0,241,True,1.5,{'minutes':5,'label':'x'*41},{'minutes':5,'label':'bad\nlabel'}, {'minutes':5,'password':'not allowed'},[],None])
def test_invalid_timer_inputs_do_not_start(timer,value):
    t,_=timer
    with pytest.raises(ValueError): t.execute('start_timer',value,now=NOW)
    assert t.snapshot()['status']=='idle'


def test_label_privacy_completion_alarm_and_sound_expiry(timer):
    t,c=timer
    t.execute('start_timer',{'minutes':1,'label':'Private appointment'},now=NOW)
    assert t.snapshot(private=True)['label']=='Timer'
    c.return_value=160
    t.tick(NOW)
    assert t.claim_chime()  # display sleep does not suppress an explicitly started timer alarm
    t.execute('start_timer',1,now=NOW)
    c.return_value=220
    t.tick(NOW)
    c.return_value=231
    assert not t.claim_chime()


@pytest.mark.parametrize('raw',[{'version':1,'status':'idle','remaining':'oops'},['bad'],{'version':1,'status':'running'}, {'version':44}, {'version':1,'status':'complete','id':'x'*36,'label':'x','duration':60,'remaining':float('inf')}])
def test_corrupt_timer_cache_is_safe(tmp_path,raw):
    storage=Storage(tmp_path/'luma.db')
    storage.set_cache('timer','active',raw)
    assert FocusTimer(storage).snapshot()['status']=='idle'


def test_api_timer_privacy_and_remote_bounds(tmp_path):
    app=create_app(data_dir=tmp_path)
    client=TestClient(app)
    start=client.post('/api/v1/commands',json={'name':'start_timer','value':{'minutes':1,'label':'Private label'}})
    assert start.status_code==200 and start.json()['result']['accepted']
    assert start.json()['snapshot']['timer']['label']=='Timer'
    assert start.json()['snapshot']['privacy_redacted']
    token=client.get('/api/v1/security/lan-token').json()['token']
    headers={'X-Luma-Token':token}
    remote=TestClient(app,client=('192.0.2.1',5000))
    assert remote.post('/api/v1/commands',headers=headers,json={'name':'cancel_timer'}).status_code==403
    assert remote.post('/api/v1/device/timer-chime',headers=headers).status_code==403
    assert client.post('/api/v1/device/timer-chime',headers={'Origin':'https://evil.example'}).status_code==403
    response=client.post('/api/v1/shortcut-command',headers=headers,json={'name':'start_timer','value':5})
    assert response.status_code==200 and response.json()['accepted'] is False
    assert 'Private label' not in response.text
    assert client.post('/api/v1/shortcut-command',headers=headers,json={'name':'start_timer','value':{'minutes':5}}).status_code==422
    assert client.patch('/api/v1/settings',json={'timer_focus_minutes':45,'timer_break_minutes':10}).status_code==200
    assert client.patch('/api/v1/settings',json={'timer_focus_minutes':True}).status_code==422
    assert remote.patch('/api/v1/settings',headers=headers,json={'timer_focus_minutes':5}).status_code==403
    assert create_app(data_dir=tmp_path).state.luma.settings.timer_focus_minutes==45


def test_voice_and_shortcut_timer_language():
    assert parse_local_command('hey luma start a twenty five minute timer').value==25
    assert parse_local_command('start a 45 minute timer').value==45
    assert parse_local_command('start a 200 minute timer').value==200
    assert parse_local_command('start a 241 minute timer') is None
    assert parse_local_command('start a 45 second timer').value=={'seconds':45,'label':'Timer'}
    assert parse_local_command('start a timer for two hours titled Laundry').value=={'seconds':7200,'label':'laundry'}
    assert parse_local_command('set timer for five mins called tea').value=={'seconds':300,'label':'tea'}
    assert parse_local_command('start a timer for one minute named bread').value=={'seconds':60,'label':'bread'}
    assert parse_local_command('start a timer for seven seconds titled stretch').value=={'seconds':7,'label':'stretch'}
    assert parse_local_command('start a timer for one hundred and twenty minutes').value==120
    assert parse_local_command('start a timer for an hour').value==60
    assert parse_local_command('start focus timer').value=='focus'
    assert parse_local_command('pause timer').name.value=='pause_timer'
    assert 'hey luma start a fifteen minute timer' in command_grammar()
    grammar=command_grammar()
    assert 'hey luma start a timer for seven seconds' in grammar
    assert 'start a one hundred twenty minute timer' in grammar
    assert 'start a timer for four hours' in grammar
    assert parse_command(b'{"name":"start_timer","value":30}').source=='siri'


def test_every_offline_timer_grammar_phrase_parses_to_a_bounded_duration():
    phrases=[phrase for phrase in command_grammar() if phrase.startswith('start a ') and 'timer' in phrase]
    assert len(phrases)==2*(120+240+4)
    for phrase in phrases:
        command=parse_local_command(phrase)
        assert command is not None, phrase
        assert command.name.value=='start_timer', phrase
        seconds=command.value*60 if type(command.value) is int else command.value['seconds']
        assert 1<=seconds<=14400, phrase


def test_voice_named_seconds_timer_persists_and_cannot_replace_existing(timer):
    t,c=timer
    command=parse_local_command('hey luma start a timer for thirty seconds called tea')
    assert command is not None
    assert t.execute(command.name.value,command.value,now=NOW,source='voice').accepted
    assert t.snapshot()['duration_seconds']==30
    assert t.snapshot()['label']=='tea'
    recovered=FocusTimer(t.storage,clock=c)
    recovered.tick(NOW+timedelta(seconds=10),trusted=True)
    assert recovered.snapshot()['remaining_seconds']==20
    other=parse_local_command('start a timer for two hours titled laundry')
    assert not t.execute(other.name.value,other.value,now=NOW,source='voice').accepted
    assert t.snapshot()['label']=='tea'


def test_chime_claim_and_bridge_failures_do_not_repeat():
    play=Mock(side_effect=OSError('no audio'))
    bridge=TimerChimeBridge(play)
    snapshot={'timer':{'id':'one','status':'complete'},'state':{'display_power':'on'},'settings':{'volume':55}}
    claim=Mock(return_value=True)
    assert bridge.apply(snapshot,claim)=='unavailable; not replayed'
    assert bridge.apply(snapshot,claim) is None
    claim.assert_called_once()
    play.assert_called_once()
    assert len(chime_pcm())==24000*2*2080//1000


def test_timer_alarm_plays_with_display_off_but_obeys_explicit_mute():
    snapshot={'timer':{'id':'one','status':'complete'},'state':{'display_power':'off'},
              'settings':{'volume':55},'display':{'quiet':True}}
    play=Mock()
    bridge=TimerChimeBridge(play)
    assert bridge.apply(snapshot,lambda:True)=='played'
    play.assert_called_once()
    snapshot['timer']['id']='two'
    snapshot['settings']['volume']=0
    assert bridge.apply(snapshot,lambda:True)=='silent'
    play.assert_called_once()
