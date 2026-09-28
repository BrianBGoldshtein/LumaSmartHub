from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from luma.agenda import day_agenda
from luma.models import CalendarEvent, Settings
from luma.service import LumaService
from luma.storage import Storage

NOW=datetime(2026,9,28,12,tzinfo=UTC)


def event(key,hour,end=None,calendar='work',**kwargs):
    start=NOW.replace(hour=0)+timedelta(hours=hour)
    return CalendarEvent(key,calendar,kwargs.pop('summary',key),start,
                         NOW.replace(hour=0)+timedelta(hours=end if end is not None else hour+1),**kwargs)


def settings():
    return Settings(timezone='UTC',visible_calendar_ids=['work','personal'],sleep_calendar_ids=['rest'])


def test_complete_day_includes_past_and_every_selected_calendar_without_limit():
    events=[event(str(i),i,calendar='work' if i%2 else 'personal') for i in range(24)]
    result=day_agenda(events,settings(),NOW,fresh=True)
    assert len(result['events'])==24
    assert result['start'].startswith('2026-09-28T00:00')
    assert result['end'].startswith('2026-09-29T00:00')
    assert result['wake'] is None and result['sleep'] is None
    assert not result['stale']


def test_sleep_bounds_and_outside_appointments_are_not_dropped():
    sleeps=[event('night',-1,7,'rest',summary='Sleep'),event('next',23,31,'rest',summary='Sleep')]
    result=day_agenda(sleeps+[event('meeting',10)],settings(),NOW,fresh=True)
    assert result['start'].startswith('2026-09-28T07:00') and result['end'].startswith('2026-09-28T23:00')
    result=day_agenda(sleeps+[event('early',5),event('late',23.5,24)],settings(),NOW,fresh=False)
    assert result['start'].startswith('2026-09-28T05:00') and result['end'].startswith('2026-09-29T00:00')
    assert len(result['events'])==2 and result['stale']


def test_cancelled_declined_other_calendars_and_other_days_filtered():
    events=[event('a',10),event('b',10,status='cancelled'),event('c',10,self_declined=True),event('d',10,calendar='hidden'),event('old',-3,-2),event('future',27,28)]
    assert [e['id'] for e in day_agenda(events,settings(),NOW,fresh=True)['events']]==['a']


def test_multiday_and_all_day_exclusive_ends():
    events=[event('span',-5,2),event('all',0,24,all_day=True),event('ended',-24,0,all_day=True)]
    assert {e['id'] for e in day_agenda(events,settings(),NOW,fresh=True)['events']}=={'span','all'}


def test_dst_day_uses_local_midnights_not_fixed_24_hours():
    prefs=settings();prefs.timezone='America/Los_Angeles'
    result=day_agenda([],prefs,datetime(2026,11,1,12,tzinfo=UTC),fresh=True)
    assert datetime.fromisoformat(result['end'])-datetime.fromisoformat(result['start'])==timedelta(hours=25)
    assert result['date']=='2026-11-01'


def test_overnight_awake_span_and_touching_sleep_intervals():
    events=[event('sleep1',-12,-8,'rest',summary='Sleep'),event('sleep2',-8,-6,'rest',summary='Sleep'),event('bed',6,14,'rest',summary='Sleep'),event('late',-3,-2)]
    result=day_agenda(events,settings(),NOW.replace(hour=1),fresh=True)
    assert result['wake'].startswith('2026-09-27T18:00')
    assert result['sleep'].startswith('2026-09-28T06:00')
    assert len(result['events'])==1


def test_snapshot_keeps_home_upcoming_and_redacts_full_day_on_lock(tmp_path):
    service=LumaService(Storage(tmp_path/'luma.db'))
    service.update_settings({'timezone':'UTC','visible_calendar_ids':['work','personal']})
    service.replace_events([event('past',8),event('future',15),event('personal',17,calendar='personal')],NOW)
    assert service.snapshot(NOW)['agenda'] is None
    service.phone_seen(NOW)
    full=service.snapshot(NOW)
    assert len(full['agenda']['events'])==3
    assert len(full['calendar'])==2
    service.phone_disconnected(NOW)
    assert service.snapshot(NOW+timedelta(minutes=2))['agenda'] is None
