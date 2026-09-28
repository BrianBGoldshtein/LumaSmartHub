import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from luma.api import create_app
from luma.countdowns import Countdowns, countdown_view
from luma.countdown_api import CountdownRuntime
from luma.integrations.google_calendar import GoogleCalendarClient
from luma.models import CalendarEvent
from luma.storage import Storage

NOW=datetime(2026,9,26,12,tzinfo=ZoneInfo('America/Los_Angeles'))


def store(tmp_path): return Countdowns(Storage(tmp_path/'luma.db'))
def manual(dates,**values):
    return dates.save_manual(**{'title':'Trip','day':'2026-10-10','timezone':'America/Los_Angeles',**values})
def google_event(**values):
    return CalendarEvent(**{'id':'abc_20261010','calendar_id':'travel','summary':'Departure',
        'start':NOW+timedelta(days=14),'end':NOW+timedelta(days=14,hours=1),
        'calendar_color':'#123456','event_color':'#abcdef',**values})


def test_manual_persistence_and_private_default(tmp_path):
    dates=store(tmp_path);item=manual(dates)
    assert dates.snapshot(NOW,private=True)==[]
    view=dates.snapshot(NOW,private=False)[0]
    assert view['label']=='14 days' and not view['public']
    assert store(tmp_path).items==dates.items
    public=dates.set_public(item['id'],item['revision'],True)
    assert dates.snapshot(NOW,private=True)[0]['title']=='Trip'
    assert dates.snapshot(NOW,private=False,quiet=True)==[]
    dates.remove(public['id'],public['revision']);assert store(tmp_path).items==[]


@pytest.mark.parametrize('values',[
    {'day':'2026-02-30'},{'day':'1999-01-01'},{'day':'2101-01-01'},
    {'at':'25:00'},{'at':'1:00'},{'timezone':'fake/zone'},
    {'public':'yes'},{'annual':1},{'title':' '},{'title':'a\nsecret'},
    {'day':'2026-03-08','at':'02:30'},
])
def test_invalid_manual_input_never_writes(tmp_path,values):
    dates=store(tmp_path)
    with pytest.raises(ValueError): manual(dates,**values)
    assert dates.items==[] and dates.storage.get_cache('countdowns','items') is None


def test_annual_february_29_policy_and_year_rollover(tmp_path):
    dates=store(tmp_path);item=manual(dates,day='2024-02-29',annual=True)
    view=countdown_view(item,datetime(2027,2,27,12,tzinfo=ZoneInfo(item['timezone'])))
    assert view['date']=='2027-02-28' and view['label']=='Tomorrow'
    view=countdown_view(item,datetime(2027,3,1,12,tzinfo=ZoneInfo(item['timezone'])))
    assert view['date']=='2028-02-29'


def test_today_passed_hours_and_dst_instant_math(tmp_path):
    dates=store(tmp_path)
    assert countdown_view(manual(dates,day='2026-09-26'),NOW)['label']=='Today'
    assert countdown_view(manual(dates,day='2026-09-27'),NOW)['label']=='Tomorrow'
    assert countdown_view(manual(dates,day='2026-09-26',at='14:30'),NOW)['label']=='3 hours'
    assert countdown_view(manual(dates,day='2026-09-26',at='10:00'),NOW)['label']=='Reached'
    old=manual(dates,day='2026-09-25')
    assert old['id'] not in {item['id'] for item in dates.snapshot(NOW,private=False)}
    repeated=manual(dates,day='2026-11-01',at='01:30')
    view=countdown_view(repeated,datetime(2026,11,1,7,30,tzinfo=UTC))
    assert view['label']=='1 hour' and view['target'].endswith('-07:00')


def test_cap_and_optimistic_edit_conflicts(tmp_path):
    dates=store(tmp_path)
    for i in range(12): manual(dates,title=str(i))
    with pytest.raises(ValueError,match='at most 12'): manual(dates)
    item=dates.items[0]
    fresh=manual(dates,title='Edited',item_id=item['id'],revision=item['revision'])
    with pytest.raises(ValueError,match='changed'): dates.remove(item['id'],item['revision'])
    assert fresh['title']=='Edited' and len(dates.items)==12


def test_no_per_snapshot_writes_and_failed_save_rolls_back(tmp_path):
    dates=store(tmp_path);manual(dates)
    dates.storage.set_cache=Mock(side_effect=OSError('disk full'))
    for i in range(100): dates.snapshot(NOW+timedelta(seconds=i),private=False)
    dates.storage.set_cache.assert_not_called()
    with pytest.raises(OSError): manual(dates,title='not saved')
    assert len(dates.items)==1


def test_corrupt_store_does_not_get_overwritten(tmp_path):
    dates=store(tmp_path);bad={'version':99,'items':[]}
    dates.storage.set_cache('countdowns','items',bad)
    restored=store(tmp_path)
    assert restored.recovery_error
    with pytest.raises(ValueError,match='recovery'): manual(restored)
    assert restored.storage.get_cache('countdowns','items')==bad


def test_google_colors_updates_stale_deleted_and_no_resurrection(tmp_path):
    dates=store(tmp_path);event=google_event()
    item=dates.pin_google(event,timezone='America/Los_Angeles',now=NOW)
    assert dates.snapshot(NOW,private=False)[0]['color']=='#abcdef'
    assert dates.snapshot(NOW+timedelta(minutes=16),private=False)[0]['state']=='stale'
    with pytest.raises(ValueError,match='already pinned'): dates.pin_google(event,timezone='UTC',now=NOW)
    updated=google_event(summary='New title',start=NOW+timedelta(days=21),event_color=None)
    assert dates.refresh(item['id'],item['revision'],event=updated,now=NOW+timedelta(minutes=5))
    view=dates.snapshot(NOW,private=False)[0]
    assert view['title']=='New title' and view['color']=='#123456' and view['label']=='21 days'
    current=dates.items[0]
    dates.refresh(current['id'],current['revision'],state='deleted',now=NOW)
    assert dates.snapshot(NOW,private=False)[0]['label']=='Removed'
    current=dates.items[0];dates.remove(current['id'],current['revision'])
    assert not dates.refresh(current['id'],current['revision'],event=event,now=NOW)
    assert dates.items==[]


def test_countdown_api_local_only_strict_and_privacy_gated(tmp_path):
    app=create_app(data_dir=tmp_path);service=app.state.luma;client=TestClient(app)
    service.display_clock_trusted=lambda:True
    values={'title':'Trip','day':'2026-10-10','timezone':'America/Los_Angeles'}
    result=client.post('/api/v1/countdowns/manual',json=values)
    assert result.status_code==200 and result.headers['cache-control']=='no-store'
    assert not result.json()['items'][0]['public']
    assert client.post('/api/v1/countdowns/manual',json={**values,'public':'yes'}).status_code==422
    token=app.state.security.get_or_create_lan_token()
    remote=TestClient(app,client=('192.0.2.33',1234))
    assert remote.get('/api/v1/countdowns',headers={'X-Luma-Token':token}).status_code==403
    service.update_settings({'onboarding_completed':True})
    assert client.get('/api/v1/countdowns').status_code==403
    assert client.get('/api/v1/state').json()['countdowns']==[]
    service.unlock_with_pin()
    assert client.get('/api/v1/countdowns').status_code==200


def test_google_api_search_is_bounded_and_pin_refetches(tmp_path):
    app=create_app(data_dir=tmp_path);client=TestClient(app);google=app.state.google
    google.authorized=Mock(return_value=True)
    google.countdown_candidates=Mock(return_value={'events':[google_event()],'next_page':'page2'})
    google.countdown_event=Mock(return_value={'state':'ready','event':google_event()})
    body={'calendar_id':'travel','start':'2027-01-01','end':'2027-02-01'}
    result=client.post('/api/v1/countdowns/search',json=body)
    assert result.status_code==200 and result.json()['next_page']=='page2'
    assert 'description' not in result.json()['events'][0]
    assert client.post('/api/v1/countdowns/search',json=body).status_code==429
    assert client.post('/api/v1/countdowns/search',json={**body,'end':'2028-01-01'}).status_code==422
    assert client.post('/api/v1/countdowns/google',json={'calendar_id':'travel','event_id':'abc_20261010'}).status_code==200
    google.countdown_event.assert_called_once()


def test_background_refresh_uses_only_pinned_ids_and_no_provider_when_empty(tmp_path):
    app=create_app(data_dir=tmp_path);service=app.state.luma
    google=Mock();google.authorized.return_value=True
    runtime=CountdownRuntime(service,google,asyncio.Lock(),clock=lambda:100)
    assert asyncio.run(runtime.refresh());google.countdown_event.assert_not_called()
    service.countdowns.pin_google(google_event(),timezone='UTC',now=NOW)
    google.countdown_event.return_value={'state':'ready','event':google_event(summary='Moved')}
    runtime.next_refresh=0
    assert asyncio.run(runtime.refresh())
    google.countdown_event.assert_called_once_with(calendar_id='travel',event_id='abc_20261010',timezone='UTC')
    assert service.countdowns.items[0]['title']=='Moved'
    assert not asyncio.run(runtime.refresh())


def test_provider_uses_exact_get_and_single_bounded_page(tmp_path):
    client=GoogleCalendarClient(Storage(tmp_path/'luma.db'));remote=MagicMock();client._service=lambda:remote
    raw={'id':'abc','summary':'Trip','start':{'date':'2027-01-02'},'end':{'date':'2027-01-03'},'colorId':'3'}
    remote.events().list().execute.return_value={'items':[raw],'nextPageToken':'next'}
    remote.events().get().execute.return_value=raw
    remote.colors().get().execute.return_value={'event':{'3':{'background':'#abcdef'}}}
    remote.calendarList().get().execute.return_value={'backgroundColor':'#123456'}
    result=client.countdown_candidates(calendar_id='travel',start=NOW,end=NOW+timedelta(days=30),timezone='UTC')
    kwargs=remote.events().list.call_args.kwargs
    assert kwargs['maxResults']==25 and kwargs['singleEvents'] and kwargs['orderBy']=='startTime'
    assert result['next_page']=='next' and result['events'][0].event_color=='#abcdef'
    assert client.countdown_event(calendar_id='travel',event_id='abc',timezone='UTC')['state']=='ready'
    assert remote.events().get.call_args.kwargs['eventId']=='abc'
    remote.events().get().execute.return_value={'status':'cancelled'}
    assert client.countdown_event(calendar_id='travel',event_id='abc',timezone='UTC')['state']=='deleted'
    remote.events().get().execute.return_value={**raw,'recurrence':['RRULE:FREQ=YEARLY']}
    with pytest.raises(ValueError,match='one occurrence'): client.countdown_event(calendar_id='travel',event_id='abc',timezone='UTC')


def test_pin_rechecks_privacy_after_provider_wait(tmp_path):
    app=create_app(data_dir=tmp_path);service=app.state.luma;client=TestClient(app)
    service.display_clock_trusted=lambda:True
    service.update_settings({'onboarding_completed':True});service.unlock_with_pin()
    app.state.google.authorized=Mock(return_value=True)
    def fetch(**kwargs):
        service.state.forced_private=True
        return {'state':'ready','event':google_event()}
    app.state.google.countdown_event=fetch
    response=client.post('/api/v1/countdowns/google',json={'calendar_id':'travel','event_id':'abc_20261010'})
    assert response.status_code==403 and service.countdowns.items==[]


def test_failed_refresh_keeps_saved_title_and_unpin_during_request_wins(tmp_path):
    app=create_app(data_dir=tmp_path);service=app.state.luma
    item=service.countdowns.pin_google(google_event(),timezone='UTC',now=NOW)
    google=Mock();google.authorized.return_value=True
    google.countdown_event.side_effect=OSError('offline')
    runtime=CountdownRuntime(service,google,asyncio.Lock(),clock=lambda:100)
    asyncio.run(runtime.refresh())
    assert service.countdowns.items[0]['title']=='Departure'
    assert service.countdowns.items[0]['state']=='stale'
    current=service.countdowns.items[0]
    def slow_result(**kwargs):
        service.countdowns.remove(current['id'],current['revision'])
        return {'state':'ready','event':google_event()}
    google.countdown_event.side_effect=slow_result;runtime.next_refresh=0
    asyncio.run(runtime.refresh())
    assert service.countdowns.items==[]
