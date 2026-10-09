from datetime import UTC, datetime, timedelta
from uuid import uuid4
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from luma.api import create_app
from luma.models import CalendarEvent, Command, CommandName
from luma.service import LumaService
from luma.storage import Storage
from luma.device_agent import DeviceBridge
from luma.device_agent import DisplayJobWorker
from luma.device_agent import native_windows_awake
from luma.portal import PortalBrowser
from luma.briefing import morning_briefing
from concurrent.futures import Future
import httpx
from luma.timer_chime import TimerChimeBridge
from luma.voice import parse_local_command
from luma.shortcut_protocol import parse_command
from test_display_cycle import Clock

NOW=datetime(2026,9,26,15,tzinfo=UTC)


def configured(tmp_path):
    storage=Storage(tmp_path/'luma.db')
    settings=storage.load_settings();settings.onboarding_completed=True
    settings.visible_calendar_ids=['work'];settings.sleep_calendar_ids=['sleep']
    storage.save_settings(settings)
    service=LumaService(storage,clock_trusted=lambda:True)
    clock=Clock();service.display.clock=clock;service.display_handoff.clock=clock
    return service,clock


def sleep(service,end=NOW+timedelta(hours=1)):
    service.replace_events([CalendarEvent('sleep','sleep','Sleep',NOW-timedelta(hours=1),end),
                            CalendarEvent('private','work','Private appointment',NOW+timedelta(hours=2),NOW+timedelta(hours=3))],NOW)
    service.unlock_with_pin(NOW)


def test_sleep_is_clock_only_private_and_quiet_then_exact_scheduled_ramp(tmp_path):
    service,clock=configured(tmp_path);sleep(service)
    state=service.snapshot(NOW)
    assert state['display']['mode']=='night-clock' and state['state']['display_power']=='on'
    assert state['privacy_redacted'] and state['calendar']==[] and state['notifications']==[] and state['departure'] is None
    assert state['agenda'] is None
    assert not service.timer_muted()
    end=NOW+timedelta(hours=1)
    assert service.snapshot(end-timedelta(seconds=1))['display']['mode']=='night-clock'
    state=service.snapshot(end)
    assert state['display']['ramp']['duration_seconds']==300 and not service.timer_muted()
    clock.advance(300)
    assert service.snapshot(end+timedelta(seconds=300))['display']['mode']=='day'
    assert not service.timer_muted()


def test_commands_use_explicit_ramp_dedupe_and_do_not_unlock(tmp_path):
    service,clock=configured(tmp_path);sleep(service)
    service.state.forced_private=True
    first=service.execute(Command(CommandName.GOOD_MORNING),NOW)
    assert first.data['briefing'] and service.snapshot(NOW)['privacy_redacted']
    ramp=service.snapshot(NOW)['display']['ramp']
    assert ramp['kind']=='morning' and ramp['duration_seconds']==20
    clock.advance(5)
    second=service.execute(Command(CommandName.GOOD_MORNING),NOW+timedelta(seconds=5))
    assert not second.data['briefing']
    assert service.snapshot(NOW+timedelta(seconds=5))['display']['ramp']['id']==ramp['id']
    service.execute(Command(CommandName.SET_BRIGHTNESS,33),NOW+timedelta(seconds=6))
    assert service.snapshot(NOW+timedelta(seconds=6))['display']['mode']=='day'
    service.execute(Command(CommandName.GOOD_NIGHT),NOW+timedelta(seconds=7))
    assert service.snapshot(NOW+timedelta(seconds=7))['display']['mode']=='night-clock'
    service.execute(Command(CommandName.SCREEN_OFF),NOW+timedelta(seconds=8))
    assert service.snapshot(NOW+timedelta(hours=2))['display']['mode']=='off'
    service.execute(Command(CommandName.WAKE),NOW+timedelta(hours=2))
    assert service.snapshot(NOW+timedelta(hours=2))['display']['mode']=='waking'


def test_temporary_wake_returns_to_sleep_and_night_preferences_persist(tmp_path):
    service,clock=configured(tmp_path);sleep(service)
    service.execute(Command(CommandName.WAKE),NOW)
    clock.advance(20)
    assert service.snapshot(NOW+timedelta(seconds=20))['display']['mode']=='day'
    assert service.snapshot(NOW+timedelta(minutes=5))['display']['mode']=='night-clock'
    service.update_settings({'night_clock_enabled':False,'night_brightness':3},NOW+timedelta(minutes=6))
    assert service.snapshot(NOW+timedelta(minutes=6))['display']['mode']=='off'
    assert service.storage.load_settings().night_brightness==3 and service.storage.load_settings().brightness==70


def test_unknown_clock_keeps_configured_hub_dark_but_not_first_run_setup(tmp_path):
    service,clock=configured(tmp_path)
    service.display_clock_trusted=lambda:False
    state=service.snapshot(NOW)
    assert state['state']['display_power']=='off' and state['display']['awaiting_clock']
    service.execute(Command(CommandName.WAKE),NOW)
    assert service.snapshot(NOW)['display']['mode']=='waking'
    fresh=LumaService(Storage(tmp_path/'fresh.db'),clock_trusted=lambda:False)
    assert fresh.snapshot(NOW)['display'] is None and fresh.state.display_power=='on'


def test_handoff_api_is_local_strict_generation_scoped_and_frame_gated(tmp_path):
    app=create_app(data_dir=tmp_path);service=app.state.luma
    service.display_clock_trusted=lambda:True
    service.update_settings({'onboarding_completed':True})
    client=TestClient(app);generation=str(uuid4())
    token=app.state.security.get_or_create_lan_token()
    remote=TestClient(app,client=('192.0.2.50',5000))
    assert remote.post('/api/v1/device/display-register',json={'generation':generation},headers={'X-Luma-Token':token}).status_code==403
    assert client.post('/api/v1/device/display-claim',json={'generation':generation}).status_code==409
    assert client.post('/api/v1/device/display-register',json={'generation':generation}).status_code==200
    revision=client.get('/api/v1/state').json()['display']['handoff']['revision']
    assert client.post('/api/v1/device/display-claim',json={'generation':generation}).json()['job'] is None
    assert client.post('/api/v1/display/frame',json={'revision':'invalid'}).status_code==422
    assert client.post('/api/v1/display/frame',json={'revision':revision},headers={'Origin':'https://evil.example'}).status_code==403
    assert client.post('/api/v1/display/frame',json={'revision':revision}).json()['accepted']
    job=client.post('/api/v1/device/display-claim',json={'generation':generation}).json()['job']
    assert job['revision']==revision and job['brightness']==70
    assert client.post('/api/v1/device/display-claim',json={'generation':generation}).json()['job'] is None
    body={'generation':generation,'revision':revision,'brightness_ok':True,'power_ok':True}
    assert client.post('/api/v1/device/display-confirm',json={**body,'brightness_ok':'yes'}).status_code==422
    assert client.post('/api/v1/device/display-confirm',json=body).json()['accepted']
    assert client.get('/api/v1/state').json()['display']['handoff']['reference_brightness']==70
    assert not client.post('/api/v1/device/display-confirm',json=body).json()['accepted']
    assert client.post('/api/v1/device/display-register',json={'generation':str(uuid4())}).status_code==200
    assert client.get('/api/v1/state').json()['display']['handoff']['reference_brightness']==100


def test_timer_alarm_remains_audible_during_sleep_and_display_off(tmp_path):
    service,clock=configured(tmp_path);sleep(service)
    state=service.snapshot(NOW)
    display,audio=Mock(),Mock();DeviceBridge(display,audio).apply(state,0)
    display.set_brightness.assert_not_called();display.power.assert_not_called()
    display.set_orientation.assert_called_once()
    played=Mock();state['timer']={'status':'complete','id':'sample'}
    state['state']['display_power']='off';state['display']['quiet']=True
    assert TimerChimeBridge(played).apply(state,lambda:True)=='played'
    played.assert_called_once()


def test_off_and_wake_voice_shortcuts_are_explicit():
    assert parse_local_command('hey luma screen off').name==CommandName.SCREEN_OFF
    assert parse_local_command('wake screen').name==CommandName.WAKE
    assert parse_command(b'{"name":"screen_off"}').name==CommandName.SCREEN_OFF


@pytest.mark.parametrize('values',[{'night_brightness':-1},{'night_brightness':101},{'night_brightness':True},{'night_clock_enabled':'yes'}])
def test_night_settings_reject_invalid_values(tmp_path,values):
    client=TestClient(create_app(data_dir=tmp_path))
    assert client.patch('/api/v1/settings',json=values).status_code==422


def test_unknown_clock_never_speaks_private_briefing_after_explicit_wake(tmp_path):
    service,clock=configured(tmp_path);sleep(service)
    service.display_clock_trusted=lambda:False
    service.execute(Command(CommandName.GOOD_MORNING),NOW)
    snapshot=service.snapshot(NOW,briefing=True)
    assert snapshot['privacy_redacted'] and snapshot['calendar']==[]
    assert morning_briefing(snapshot)=='Good morning. My clock is still syncing; private details stay hidden.'


def test_bridge_snapshot_cannot_consume_wake_completion_before_broadcast(tmp_path):
    service,clock=configured(tmp_path);sleep(service)
    service.execute(Command(CommandName.WAKE),NOW)
    service.timer_tick(NOW)
    queue=service.subscribe()
    clock.advance(20)
    assert service.snapshot(NOW+timedelta(seconds=20))['display']['mode']=='day'
    assert queue.empty()  # Snapshot is read-only with respect to broadcasts.
    service.timer_tick(NOW+timedelta(seconds=20))
    assert queue.get_nowait()['type']=='display.updated'
    service.timer_tick(NOW+timedelta(seconds=21))
    assert queue.empty()  # Stable day state does not create a per-second stream.


@pytest.mark.parametrize('endpoint,payload',[
    ('/api/v1/voice/command',{'text':'hey luma good morning'}),
    ('/api/v1/shortcut-command',{'name':'good_morning'}),
])
def test_live_command_routes_honor_single_briefing(tmp_path,endpoint,payload):
    app=create_app(data_dir=tmp_path);service=app.state.luma
    service.display_clock_trusted=lambda:True
    service.update_settings({'onboarding_completed':True,'voice_enabled':True})
    client=TestClient(app)
    headers={'X-Luma-Token':app.state.security.get_or_create_lan_token()}
    briefing_module = 'luma.voice_accounts' if endpoint == '/api/v1/voice/command' else 'luma.api'
    with patch(briefing_module+'.morning_briefing',return_value='One morning briefing') as briefing:
        first=client.post(endpoint,json=payload,headers=headers)
        second=client.post(endpoint,json=payload,headers=headers)
    assert first.status_code==second.status_code==200
    assert first.json()['message']=='One morning briefing'
    assert second.json()['message']!='One morning briefing'
    briefing.assert_called_once()


@pytest.mark.parametrize('driver_crash',[False,True])
def test_display_worker_never_waits_on_ddc_and_reports_unknown_on_crash(tmp_path,driver_crash):
    service,clock=configured(tmp_path)
    state=service.snapshot(NOW)
    executor=Mock();future=Future();executor.submit.return_value=future
    worker=DisplayJobWorker(Mock(),executor);calls=[];revision=str(uuid4())
    def handle(request):
        import json
        body=json.loads(request.content);calls.append((request.url.path,body))
        if request.url.path.endswith('display-claim'):
            return httpx.Response(200,json={'job':{'revision':revision,'power':True,'brightness':70}})
        return httpx.Response(200,json={'accepted':True})
    with httpx.Client(base_url='http://testserver',transport=httpx.MockTransport(handle)) as client:
        worker.poll(client,state)
        assert not future.done() and executor.submit.call_count==1
        worker.poll(client,state)  # Returns with unfinished future; no duplicate work.
        assert len(calls)==2 and executor.submit.call_count==1
        if driver_crash: future.set_exception(ValueError('Synthetic driver failure'))
        else: future.set_result({'revision':revision,'brightness_ok':True,'power_ok':True})
        worker.poll(client,state)
    confirmations=[body for path,body in calls if path.endswith('display-confirm')]
    assert confirmations==[{'generation':worker.generation,'revision':revision,
                           'brightness_ok':not driver_crash,'power_ok':not driver_crash}]


def test_display_worker_reregisters_after_backend_restart(tmp_path):
    service,clock=configured(tmp_path);state=service.snapshot(NOW)
    worker=DisplayJobWorker(Mock(),Mock());calls=[]
    def handle(request):
        calls.append(request.url.path)
        return httpx.Response(409 if request.url.path.endswith('display-claim') else 200,json={})
    with httpx.Client(base_url='http://testserver',transport=httpx.MockTransport(handle)) as client:
        worker.poll(client,state);assert not worker.registered
        worker.poll(client,state);assert not worker.registered
    assert sum(path.endswith('display-register') for path in calls)==2


def test_chime_report_preserves_strict_hardware_status_validation(tmp_path):
    client=TestClient(create_app(data_dir=tmp_path))
    assert client.post('/api/v1/device/report',json={'controls':{'timer_chime':'silent'}}).status_code==200
    assert client.post('/api/v1/device/report',json={'controls':{'power':'played'}}).status_code==422
    assert client.post('/api/v1/device/report',json={'controls':{'timer_chime':'replayed'}}).status_code==422


@pytest.mark.parametrize('mode,expected',[('day',True),('off',False),('night-clock',False),('waking',False)])
def test_native_helpers_are_allowed_only_in_day_mode(mode,expected):
    assert native_windows_awake({'state':{'display_power':'on'},'display':{'mode':mode}}) is expected
    assert not native_windows_awake({'state':{'display_power':'off'}})
    assert native_windows_awake({'state':{'display_power':'on'},'display':None})


def test_native_portal_closes_at_night_and_old_requests_do_not_replay():
    portal=PortalBrowser(Mock());process=Mock();process.poll.return_value=None
    portal.process=process
    portal.apply('previous-request',False)
    process.terminate.assert_called_once();process.wait.assert_called_once_with(timeout=1)
    assert portal.process is None
    portal.apply('previous-request',True)
    portal.launch.assert_not_called()
