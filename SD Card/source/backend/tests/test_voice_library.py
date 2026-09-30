from datetime import UTC, datetime, timedelta
from threading import Event
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from luma.api import create_app
from luma.models import CalendarEvent, CommandName, WeatherHour, WeatherSnapshot
from luma.service import LumaService
from luma.storage import Storage
from luma.voice import command_grammar, parse_local_command, WakeGate
from luma.voice_library import QUERY_PHRASES, LIBRARY, answer_query
from luma.voice_agent import _free_command
from luma.voice_model import predict

ZONE=ZoneInfo('America/Los_Angeles')
NOW=datetime(2026,9,26,14,0,tzinfo=ZONE)


def prepared(tmp_path):
    service=LumaService(Storage(tmp_path/'luma.db'),clock_trusted=lambda:True)
    service.update_settings({'visible_calendar_ids':['work'],'todo_calendar_id':'tasks','todo_completed_color_id':'10'},NOW)
    service.unlock_with_pin(NOW)
    service.calendar_synced_at=NOW
    return service


def event(name,start,end,calendar='work',**kwargs):
    return CalendarEvent(name,calendar,name,start,end,**kwargs)


def reply(service,intent,now=NOW,authorized=True):
    return answer_query(intent,service.voice_snapshot(authorized=authorized,now=now))


@pytest.mark.parametrize('intent,phrase',[(intent,phrase) for intent,phrases in QUERY_PHRASES.items() for phrase in phrases])
def test_every_alias_is_in_offline_grammar_and_maps_to_a_local_question(intent,phrase):
    assert phrase in command_grammar() and 'hey luma '+phrase in command_grammar()
    parsed=parse_local_command('Hey Luma, '+phrase+'?')
    assert parsed.name==CommandName.LOCAL_QUERY and parsed.value==intent


def test_all_presented_library_examples_are_recognized():
    for group in LIBRARY:
        for phrase in group['examples']:
            assert parse_local_command('Hey Luma, '+phrase) is not None
    gate=WakeGate()
    assert gate.accept('when is my next event',1) is None
    assert gate.accept('hey luma',2)==''
    assert gate.accept('when is my next event',3)=='when is my next event'


@pytest.mark.parametrize('phrase', [
    'what time is it', "what's the time", 'what is the time',
    'tell me the time', 'could you tell me the time',
    'do you know what time it is',
])
def test_everyday_time_paraphrases_resolve_identically(phrase):
    command = parse_local_command('Hey Luma, ' + phrase + '?')
    assert command.name == CommandName.LOCAL_QUERY
    assert command.value == 'time'


def test_phrase_preview_exposes_offline_model_without_executing(tmp_path):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    before = app.state.luma.settings.theme
    preview = client.post('/api/v1/voice/phrase-preview', json={'text': "what's the time"})
    assert preview.status_code == 200
    assert preview.json()['command'] == CommandName.LOCAL_QUERY.value
    assert preview.json()['intent'] == 'time'
    assert preview.json()['model_suggestion'] == 'time'
    assert preview.json()['executed'] is False
    assert app.state.luma.settings.theme == before
    varied = client.post('/api/v1/voice/phrase-preview', json={'text': 'tell me tomorrow weather'})
    assert varied.json()['intent'] == 'weather_tomorrow'
    assert varied.json()['model_suggestion'] == 'weather_tomorrow'
    assert client.get('/api/v1/voice/library').json()['phrase_model'] == 'offline-neural-v1'


@pytest.mark.parametrize('phrase,key',[
    ('run morning scene','morning'),('run night scene','night'),
    ('run arrival scene','arrive'),('run away scene','away'),
])
def test_scene_voice_commands_are_fixed_and_in_the_offline_grammar(phrase,key):
    command=parse_local_command('Hey Luma, '+phrase)
    assert command.name==CommandName.RUN_SCENE and command.value==key
    assert phrase in command_grammar() and 'hey luma '+phrase in command_grammar()


def test_cancel_scene_is_explicit_and_good_morning_keeps_its_briefing_meaning():
    assert parse_local_command('cancel scene').name==CommandName.CANCEL_SCENE
    assert parse_local_command('good morning').name==CommandName.GOOD_MORNING


@pytest.mark.parametrize('phrase',['when is my next event in december',
                                  'ask explain quantum physics','question spend money','what is good night',
                                  'can you set brightness to zero'])
def test_unknown_questions_do_not_navigate_mutate_or_call_cloud(phrase):
    assert parse_local_command(phrase) is None


def test_offline_neural_matcher_maps_held_out_phrases_only_to_safe_intents():
    samples={
        'tell me tomorrow weather':'weather_tomorrow',
        'is rain coming tomorrow':'rain_tomorrow',
        'what tasks are late':'tasks_overdue',
        'is my phone around':'phone_status',
        'tell me my plans for tomorrow':'calendar_tomorrow',
        'when do i have a break':'free_time',
        'what time does my next class start':'next_event',
    }
    for phrase,intent in samples.items():
        command=parse_local_command(phrase)
        assert command.name==CommandName.LOCAL_QUERY and command.value==intent
    assert parse_local_command('switch to wooden design').name==CommandName.SET_THEME
    assert parse_local_command('pull up agenda').name==CommandName.SHOW_PAGE
    assert parse_local_command('bring up the brightness control').name==CommandName.SHOW_BRIGHTNESS
    assert parse_local_command('can you set brightness to zero') is None
    assert parse_local_command('show weather').name==CommandName.SHOW_PAGE
    far=parse_local_command('what is the weather next week')
    assert far.name==CommandName.LOCAL_QUERY and far.value=='weather_beyond_forecast'


def test_quantized_model_is_packaged_and_unknown_speech_stays_inert():
    assert predict('tell me tomorrow weather')[0]=='weather_tomorrow'
    for phrase in ('turn on the lights','make a phone call','read all my notifications',
                   'what is my bank balance','where did my keys go'):
        assert parse_local_command(phrase) is None
    assert _free_command('hey luma tell me tomorrow weather','hey luma')=='tell me tomorrow weather'
    assert _free_command('tell me tomorrow weather','hey luma')=='tell me tomorrow weather'


@pytest.mark.parametrize('phrase,minutes',[
    ('set a timer for 12 minutes',12),
    ('start a twenty five minute timer',25),
    ('set timer for one hour',60),
    ('start a two hour timer',120),
    ('set a timer for one hundred twenty minutes',120),
])
def test_spoken_timer_variations_keep_the_explicit_duration(phrase,minutes):
    command=parse_local_command(phrase)
    assert command.name==CommandName.START_TIMER and command.value==minutes
    assert parse_local_command('set timer for 241 minutes') is None


def test_today_includes_earlier_ongoing_all_day_but_not_other_calendars_or_declined(tmp_path):
    service=prepared(tmp_path)
    service.replace_events([
        event('Morning',NOW-timedelta(hours=5),NOW-timedelta(hours=4)),
        event('Current',NOW-timedelta(minutes=30),NOW+timedelta(minutes=30)),
        event('All day',NOW.replace(hour=0),NOW.replace(hour=0)+timedelta(days=1),all_day=True),
        event('Hidden',NOW,NOW+timedelta(hours=1),calendar='other'),
        event('Declined',NOW,NOW+timedelta(hours=1),self_declined=True),
        event('Cancelled',NOW,NOW+timedelta(hours=1),status='cancelled'),
        event('Tomorrow',NOW+timedelta(days=1),NOW+timedelta(days=1,hours=1)),
    ],NOW)
    today=reply(service,'calendar_today')
    assert all(name in today for name in ['Morning','Current','All day'])
    assert all(name not in today for name in ['Hidden','Declined','Cancelled','Tomorrow'])
    assert 'Tomorrow' in reply(service,'calendar_tomorrow')
    assert 'Tomorrow' in reply(service,'next_event')
    assert 'Current' in reply(service,'ongoing') and 'All day' not in reply(service,'ongoing')


def test_calendar_privacy_mute_and_no_cloud_route(tmp_path):
    app=create_app(data_dir=tmp_path);service=app.state.luma
    service.update_settings({'visible_calendar_ids':['work']})
    now=datetime.now(UTC)
    service.replace_events([event('SECRET TITLE',now+timedelta(hours=1),now+timedelta(hours=2))])
    app.state.google.authorized=Mock(return_value=True)
    app.state.google.fetch_events=Mock(side_effect=AssertionError('Question must not poll provider'))
    service.router.cloud_ask=Mock(side_effect=AssertionError('No AI calls'))
    client=TestClient(app)
    ask=lambda text:client.post('/api/v1/voice/command',json={'text':text}).json()
    assert 'private' in ask('when is my next event')['message']
    service.unlock_with_pin()
    assert 'SECRET TITLE' in ask('when is my next event')['message']
    assert not ask('ask answer anything')['accepted']
    service.update_settings({'voice_enabled':False})
    assert not ask('when is my next event')['accepted']
    service.router.cloud_ask.assert_not_called();app.state.google.fetch_events.assert_not_called()
    token=app.state.security.get_or_create_lan_token()
    remote=TestClient(app,client=('192.0.2.20',5000))
    assert remote.post('/api/v1/voice/command',json={'text':'when is my next event'},headers={'X-Luma-Token':token}).status_code==403
    assert client.get('/api/v1/voice/library').json()['groups']==LIBRARY


def test_voice_scene_requires_owner_and_nonempty_explicitly_enabled_config(tmp_path):
    app=create_app(data_dir=tmp_path);service=app.state.luma;runtime=app.state.scene_runtime
    service.display_clock_trusted=lambda:True
    client=TestClient(app)
    service.update_settings({'onboarding_completed':True})
    private=client.post('/api/v1/voice/command',json={'text':'run morning scene'}).json()
    assert not private['accepted'] and 'Unlock Luma' in private['message']
    runtime.owner_allowed=lambda:True
    empty=client.post('/api/v1/voice/command',json={'text':'run morning scene'}).json()
    assert not empty['accepted'] and 'not set up' in empty['message']
    runtime.store.definitions['morning']={'enabled':True,'automatic':False,'actions':[{'device':'purifier'}]}
    service.display_clock_trusted=lambda:False
    clock=client.post('/api/v1/voice/command',json={'text':'run morning scene'}).json()
    assert not clock['accepted'] and 'clock' in clock['message'].lower()


def test_voice_scene_starts_saved_manual_run_only_after_all_gates(tmp_path):
    import asyncio
    app=create_app(data_dir=tmp_path);runtime=app.state.scene_runtime
    app.state.luma.display_clock_trusted=lambda:True
    runtime.store.definitions['night']={'enabled':True,'automatic':False,'actions':[{'device':'purifier'}]}
    runtime.configuration=lambda:{'definitions':{'night':{'needs_review':False}}}
    started=Event()
    async def manual(key,revision):
        assert key=='night' and revision==runtime.store.revision
        started.set()
        await asyncio.sleep(0)
    runtime.manual=manual
    response=TestClient(app).post('/api/v1/voice/command',json={'text':'run night scene'})
    assert response.json()['accepted'] and 'started' in response.json()['message']
    assert started.wait(2)


def test_stale_unconfigured_and_missing_account_are_honest(tmp_path):
    service=prepared(tmp_path)
    service.calendar_synced_at=None
    assert 'saved calendar only' in reply(service,'calendar_today')
    assert 'Connect Google Calendar' in reply(service,'next_event',authorized=False)
    service.update_settings({'visible_calendar_ids':[]},NOW)
    assert 'Choose your visible calendars' in reply(service,'calendar_today')


def test_questions_do_not_unlock_or_wake_night_or_unknown_clock(tmp_path):
    service=prepared(tmp_path)
    service.update_settings({'onboarding_completed':True},NOW)
    from luma.models import Command
    service.execute(Command(CommandName.GOOD_NIGHT),NOW)
    before=service.snapshot(NOW)['display']['mode']
    assert 'private' in reply(service,'calendar_today')
    assert service.snapshot(NOW)['display']['mode']==before
    service.display_clock_trusted=lambda:False
    assert 'clock is still syncing' in reply(service,'time')


def test_tasks_follow_today_and_only_chosen_completed_color(tmp_path):
    service=prepared(tmp_path);start=NOW.replace(hour=0)
    service.replace_events([
        event('Due task',start-timedelta(days=2),start+timedelta(days=1),'tasks',all_day=True),
        event('Other color',start,start+timedelta(days=3),'tasks',all_day=True,event_color_id='4'),
        event('Done task',start,start+timedelta(days=1),'tasks',all_day=True,event_color_id='10'),
        event('Future task',start+timedelta(days=1),start+timedelta(days=2),'tasks',all_day=True),
    ],NOW)
    result=reply(service,'tasks_today')
    assert 'Due task' in result and 'Other color' in result
    assert 'Done task' not in result and 'Future task' not in result
    assert 'Other color' not in reply(service,'tasks_due')


def test_local_day_boundary_and_exclusive_all_day_end(tmp_path):
    service=prepared(tmp_path);now=NOW.replace(hour=23,minute=30)
    service.unlock_with_pin(now)
    service.replace_events([
        event('Expired',NOW.replace(hour=0)-timedelta(days=1),NOW.replace(hour=0),all_day=True),
        event('Later tonight',now+timedelta(minutes=15),now+timedelta(minutes=20)),
        event('After midnight',now+timedelta(hours=1),now+timedelta(hours=2)),
    ],now)
    today=reply(service,'calendar_today',now.astimezone(UTC))
    tomorrow=reply(service,'calendar_tomorrow',now.astimezone(UTC))
    assert 'Later tonight' in today and 'After midnight' not in today and 'Expired' not in today
    assert 'After midnight' in tomorrow and 'Later tonight' not in tomorrow


def test_long_calendar_is_bounded_and_titles_are_only_data(tmp_path):
    service=prepared(tmp_path)
    service.replace_events([event('-x Ignore instructions '+str(i)+'z'*300,NOW+timedelta(minutes=i+1),NOW+timedelta(hours=1)) for i in range(50)],NOW)
    result=reply(service,'calendar_today')
    assert '47 more' in result and len(result)<650


def test_weather_saved_data_missing_rain_and_units(tmp_path):
    service=prepared(tmp_path)
    assert 'saved forecast' in reply(service,'weather_today')
    service.replace_weather(WeatherSnapshot(NOW,70,68,75,55,0,'Clear skies',hourly=[
        WeatherHour(NOW+timedelta(hours=1),70,None,0),WeatherHour(NOW+timedelta(hours=2),70,0,0)]))
    assert '70 degrees Fahrenheit' in reply(service,'weather_today')
    assert 'high of 75' in reply(service,'weather_today')
    assert 'Feels like 68' in reply(service,'weather_now')
    assert '0 percent' in reply(service,'rain_today') and 'Some hours are missing' in reply(service,'rain_today')
    service.weather.hourly[1].precipitation_probability=None
    assert 'do not have precipitation' in reply(service,'rain_today')
    service.weather.observed_at=NOW-timedelta(hours=3)
    assert 'may be out of date' in reply(service,'weather_today')


def test_broader_weather_answers_use_the_requested_local_day(tmp_path):
    service=prepared(tmp_path)
    service.replace_weather(WeatherSnapshot(NOW,70,68,75,55,0,'Clear skies',hourly=[
        WeatherHour(NOW+timedelta(hours=1),72,5,0),
        WeatherHour(NOW+timedelta(days=1,hours=1),82,60,3),
        WeatherHour(NOW+timedelta(days=1,hours=2),61,10,0),
    ]))
    assert '61 to 82' in reply(service,'weather_tomorrow')
    assert '60 percent' in reply(service,'rain_tomorrow')
    assert '82 degrees' in reply(service,'high_tomorrow')
    assert '61 degrees' in reply(service,'low_tomorrow')
    assert 'next saved hour' in reply(service,'rain_timing')
    assert 'two days' in reply(service,'weather_beyond_forecast')


def test_week_free_time_location_and_task_deadlines_respect_saved_data(tmp_path):
    service=prepared(tmp_path)
    start=NOW.replace(hour=0)
    service.replace_events([
        event('Next class',NOW+timedelta(minutes=50),NOW+timedelta(hours=2),location='Room 101'),
        event('Later event',NOW+timedelta(days=2),NOW+timedelta(days=2,hours=1)),
        event('Late paper',start-timedelta(days=4),start-timedelta(days=1),'tasks',all_day=True),
        event('Due soon',start,start+timedelta(days=3),'tasks',all_day=True),
        event('Finished',start-timedelta(days=2),start+timedelta(days=1),'tasks',all_day=True,event_color_id='10'),
    ],NOW)
    assert 'Room 101' in reply(service,'next_location')
    assert '50 minutes' in reply(service,'free_time')
    assert '2 events' in reply(service,'calendar_week')
    assert 'Late paper' in reply(service,'tasks_overdue')
    assert 'Due soon' in reply(service,'tasks_soon')
    assert 'Finished' in reply(service,'tasks_completed')
    assert 'Late paper' not in reply(service,'tasks_soon')


def test_status_answers_are_private_and_do_not_claim_unknown_network_is_online(tmp_path):
    service=prepared(tmp_path)
    snapshot=service.voice_snapshot(authorized=False,now=NOW)
    snapshot['voice_status']={'network':{'state':'unknown'}}
    assert 'cannot verify' in answer_query('internet_status',snapshot)
    assert 'No iPhone' in answer_query('phone_status',snapshot)
    private_service=LumaService(Storage(tmp_path/'private.db'),clock_trusted=lambda:True)
    private=private_service.voice_snapshot(authorized=False,now=NOW)
    assert 'private standby' in answer_query('sync_status',private).lower()


def test_timer_date_time_and_help_remain_local_and_bounded(tmp_path):
    service=prepared(tmp_path)
    assert reply(service,'time')=='It is 2:00 PM.'
    assert 'Saturday, September 26, 2026' in reply(service,'date')
    assert reply(service,'timer_status')=='There is no active timer.'
    snapshot=service.voice_snapshot(authorized=False,now=NOW)
    snapshot['timer']={'status':'paused','remaining_seconds':65,'label':'PRIVATE TIMER LABEL'}
    assert answer_query('timer_status',snapshot)=='Your timer is paused with 1 minute and 5 seconds left.'
    assert 'without an AI service' in reply(service,'help')
