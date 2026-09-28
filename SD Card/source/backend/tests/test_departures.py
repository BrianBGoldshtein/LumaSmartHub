from dataclasses import replace, asdict
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from luma.api import create_app
from luma.departures import Departures, occurrence_key
from luma.integrations.google_calendar import parse_google_event
from luma.models import Settings, CalendarEvent
from luma.storage import Storage

NOW=datetime(2026,9,26,20,tzinfo=UTC)

def setup(tmp_path):
    engine=Departures(Storage(tmp_path/'test.db'))
    settings=Settings(departure_enabled=True,departure_calendar_ids=['personal'])
    event=CalendarEvent('one','personal','Dinner',NOW+timedelta(minutes=25),NOW+timedelta(minutes=85),calendar_color='#123456')
    return engine,settings,event

def test_window_boundaries_defaults_and_no_tick_writes(tmp_path):
    engine,settings,event=setup(tmp_path)
    with patch.object(engine.storage,'set_cache') as write:
        assert engine.snapshot([event],settings,NOW-timedelta(minutes=5,seconds=1)) is None
        result=engine.snapshot([event],settings,NOW-timedelta(minutes=5))
        assert result['depart_at']==(NOW+timedelta(minutes=10)).isoformat()
        assert result['prep_minutes']==5 and result['travel_minutes']==10 and result['color']=='#123456'
        assert engine.snapshot([event],settings,event.start-timedelta(seconds=1))
        assert engine.snapshot([event],settings,event.start) is None
        write.assert_not_called()

@pytest.mark.parametrize('changes',[{'status':'cancelled'},{'all_day':True},{'self_declined':True},{'summary':' Sleep '},{'calendar_id':'unselected'},{'virtual_only':True}])
def test_ineligible_events_are_silent(tmp_path,changes):
    engine,settings,event=setup(tmp_path)
    assert engine.snapshot([replace(event,**changes)],settings,NOW) is None

def test_opt_in_virtual_privacy_freshness_and_overlap_order(tmp_path):
    engine,settings,event=setup(tmp_path)
    virtual=replace(event,virtual_only=True)
    assert engine.snapshot([virtual],replace(settings,departure_include_virtual=True),NOW)
    assert engine.snapshot([event],settings,NOW,private=True) is None
    assert engine.snapshot([event],settings,NOW,fresh=False) is None
    assert engine.snapshot([event],replace(settings,departure_enabled=False),NOW) is None
    earlier=replace(event,id='two',start=event.start-timedelta(minutes=1))
    for events in ([event,earlier],[earlier,event]):assert engine.snapshot(events,settings,NOW)['key']==occurrence_key(earlier)

def test_snooze_dismiss_restart_and_reschedule(tmp_path):
    engine,settings,event=setup(tmp_path)
    args=dict(key=occurrence_key(event),events=[event],settings=settings,now=NOW)
    engine.act(action='snooze',**args)
    restored=Departures(engine.storage)
    assert restored.snapshot([event],settings,NOW+timedelta(minutes=4,seconds=59)) is None
    assert restored.snapshot([event],settings,NOW+timedelta(minutes=5))
    restored.act(action='dismiss',**args)
    assert Departures(engine.storage).snapshot([event],settings,NOW) is None
    assert restored.snapshot([replace(event,start=event.start+timedelta(minutes=1))],settings,NOW)
    assert restored.snapshot([replace(event,summary='Renamed',etag='changed',event_color='#abcdef')],settings,NOW) is None
    assert occurrence_key(event)==occurrence_key(replace(event,start=event.start.astimezone(ZoneInfo('America/Los_Angeles')),end=event.end.astimezone(ZoneInfo('America/Los_Angeles'))))

def test_per_occurrence_estimates_and_invalid_requests(tmp_path):
    engine,settings,event=setup(tmp_path)
    args=dict(key=occurrence_key(event),events=[event],settings=settings,now=NOW)
    engine.act(action='override',prep=7,travel=15,**args)
    result=Departures(engine.storage).snapshot([event],settings,NOW)
    assert result['depart_at']==(event.start-timedelta(minutes=22)).isoformat()
    assert settings.departure_prep_minutes==5
    for action,prep,travel in [('invalid',None,None),('override',True,5),('override',0,241),('snooze',1,None)]:
        with pytest.raises(ValueError):engine.act(action=action,prep=prep,travel=travel,**args)
    with pytest.raises(ValueError):engine.act(action='dismiss',**{**args,'events':[replace(event,status='cancelled')]})

def test_midnight_and_dst_use_elapsed_minutes(tmp_path):
    engine,settings,event=setup(tmp_path)
    start=datetime(2026,11,1,1,10,tzinfo=ZoneInfo('America/Los_Angeles'),fold=1)
    event=replace(event,start=start,end=start+timedelta(hours=2))
    result=engine.snapshot([event],settings,datetime(2026,11,1,8,45,tzinfo=UTC))
    assert result['depart_at']=='2026-11-01T08:55:00+00:00'
    start=datetime(2026,9,27,0,5,tzinfo=UTC)
    result=engine.snapshot([replace(event,start=start,end=start+timedelta(hours=1))],settings,start-timedelta(minutes=20))
    assert result['depart_at']=='2026-09-26T23:50:00+00:00'

@pytest.mark.parametrize('location,conference,expected',[('https://meet.google.com/abc',False,True),('https://us02.zoom.us/j/1',False,True),('https://maps.google.com/place',False,False),('Room 2',True,False),('',True,True),('Online',False,True),('https://zoom.us.evil.example',False,False)])
def test_minimal_google_metadata(location,conference,expected):
    raw={'id':'one','start':{'dateTime':NOW.isoformat()},'end':{'dateTime':(NOW+timedelta(hours=1)).isoformat()},'location':location,
         'attendees':[{'self':True,'responseStatus':'declined','email':'do-not-retain@example.invalid'}]}
    if conference:raw['conferenceData']={'entryPoints':[{'uri':'https://meet.google.com/abc'}]}
    event=parse_google_event(raw,'personal','UTC')
    assert event.virtual_only is expected and event.self_declined
    assert 'attendees' not in asdict(event) and 'conferenceData' not in asdict(event)

def test_bounded_cache_corruption_and_expiry(tmp_path):
    engine,settings,event=setup(tmp_path)
    engine.storage.set_cache('departures','occurrences',{'bad':{},'a'*64:{'expires':'bad'},'b'*64:{'expires':'2026-01-01'},
        occurrence_key(event):{'expires':event.start.isoformat(),'prep':False,'travel':10,'snooze_until':(event.start+timedelta(days=1)).isoformat()}})
    restored=Departures(engine.storage)
    assert len(restored.records)==1 and 'prep' not in restored.records[occurrence_key(event)]
    assert restored.records[occurrence_key(event)]['snooze_until']==event.start.isoformat()
    restored.records={f'{i:064x}':{'expires':(NOW+timedelta(minutes=i-10)).isoformat()} for i in range(300)}
    restored.act(key=occurrence_key(event),action='dismiss',events=[event],settings=settings,now=NOW)
    assert len(restored.records)==256 and occurrence_key(event) in restored.records
    assert all(datetime.fromisoformat(v['expires'])>NOW for v in restored.records.values())
    distant=replace(event,start=NOW+timedelta(hours=10),end=NOW+timedelta(hours=11))
    restored.act(key=occurrence_key(distant),action='dismiss',events=[distant],settings=settings,now=NOW)
    assert len(restored.records)==256 and occurrence_key(distant) in Departures(engine.storage).records

def test_api_local_private_fresh_current_and_persisted(tmp_path):
    app=create_app(data_dir=tmp_path);service=app.state.luma;now=datetime.now(UTC)
    service.update_settings({'departure_enabled':True,'departure_calendar_ids':['personal']})
    event=CalendarEvent('one','personal','Dinner',now+timedelta(minutes=25),now+timedelta(hours=1))
    service.replace_events([event]);service.calendar_synced_at=now;service.calendar_sync_error=False
    client=TestClient(app);body={'key':occurrence_key(event),'action':'dismiss'}
    assert client.post('/api/v1/departures/action',json=body).status_code==403
    service.unlock_with_pin()
    assert client.get('/api/v1/state').json()['departure']['title']=='Dinner'
    for bad in ({**body,'key':'invalid'},{**body,'action':'overwrite'},{**body,'extra':True},{**body,'action':'override','prep':True,'travel':4}):
        assert client.post('/api/v1/departures/action',json=bad).status_code==422
    assert client.post('/api/v1/departures/action',json={**body,'key':'f'*64}).status_code==409
    token=app.state.security.get_or_create_lan_token();remote=TestClient(app,client=('192.0.2.20',5000))
    assert remote.post('/api/v1/departures/action',json=body,headers={'X-Luma-Token':token}).status_code==403
    assert remote.patch('/api/v1/settings',json={'departure_enabled':False},headers={'X-Luma-Token':token}).status_code==403
    service.calendar_synced_at=now-timedelta(minutes=11)
    assert client.get('/api/v1/state').json()['departure'] is None
    assert client.post('/api/v1/departures/action',json=body).status_code==409
    service.calendar_synced_at=now
    service.calendar_sync_error=True
    assert client.get('/api/v1/state').json()['departure'] is None
    service.calendar_sync_error=False
    service.calendar_synced_at=now+timedelta(hours=1)
    assert client.get('/api/v1/state').json()['departure'] is None
    service.calendar_synced_at=now
    with patch.object(app.state.google,'_service',side_effect=AssertionError('No Google writes')):
        result=client.post('/api/v1/departures/action',json=body)
        assert result.status_code==200 and result.json()['departure'] is None
    assert occurrence_key(event) in create_app(data_dir=tmp_path).state.luma.departures.records

def test_existing_sync_includes_only_enabled_departure_calendars(tmp_path):
    app=create_app(data_dir=tmp_path);service=app.state.luma;client=TestClient(app)
    service.update_settings({'visible_calendar_ids':['agenda'],'departure_calendar_ids':['outings','agenda']})
    with patch.object(app.state.google,'authorized',return_value=True),patch.object(app.state.google,'fetch_events',return_value=[]) as fetch:
        assert client.post('/api/v1/google/sync').status_code==200
        assert fetch.call_args.args[0]==['agenda']
        service.update_settings({'departure_enabled':True})
        assert client.post('/api/v1/google/sync').status_code==200
        assert fetch.call_args.args[0]==['agenda','outings']
        assert client.get('/api/v1/onboarding').json()['summary']['departure_calendars']==2

@pytest.mark.parametrize('patch_values',[{'departure_enabled':'yes'},{'departure_calendar_ids':['']},{'departure_prep_minutes':True},{'departure_travel_minutes':241},{'departure_calendar_ids':['c']*51}])
def test_setting_validation(tmp_path,patch_values):
    client=TestClient(create_app(data_dir=tmp_path))
    assert client.patch('/api/v1/settings',json=patch_values).status_code==422
