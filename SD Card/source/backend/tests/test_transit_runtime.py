import asyncio
from datetime import UTC,datetime,timedelta
from threading import Event
from unittest.mock import Mock

from fastapi.testclient import TestClient
import httpx
import pytest

from luma.api import create_app
from luma.service import LumaService
from luma.storage import Storage
from luma.transit import Transit
from luma.transit_runtime import TransitRuntime,TransitDirectory,delivery_ok
from luma.transit_transport import TransitBudget,TransitTransport,TransitQuota,TransitUnavailable

NOW=datetime(2026,9,26,20,tzinfo=UTC)
TOKEN='synthetic_511_token_for_tests_only'


def favorite(service,**changes):
    return service.transit.save(**{'title':'Station','operator_id':'OP','operator_name':'Caltrain demo','agency':'RT',
        'stop_id':'STOP','stop_name':'Station','monitored':True,**changes})


def feed(endpoint='StopMonitoring',empty=False):
    live=endpoint=='StopMonitoring';call={'StopPointRef':'STOP','AimedDepartureTime':(NOW+timedelta(minutes=20)).isoformat(),
                                        'ExpectedDepartureTime':(NOW+timedelta(minutes=18)).isoformat()}
    journey={'LineRef':'R','DirectionRef':'N','Monitored':True,'DestinationName':'Campus',
             ('MonitoredCall' if live else 'TargetedCall'):call}
    visit={'RecordedAtTime':NOW.isoformat(),('MonitoredVehicleJourney' if live else 'TargetedVehicleJourney'):journey}
    delivery={'ResponseTimestamp':NOW.isoformat(),('MonitoredStopVisit' if live else 'TimetabledStopVisit'):[] if empty else [visit]}
    return {'Siri':{'ServiceDelivery':{('StopMonitoringDelivery' if live else 'StopTimetableDelivery'):delivery}}}


def runtime(tmp_path):
    service=LumaService(Storage(tmp_path/'luma.db'));service.transit.set_token(TOKEN)
    clock=[1000.0];transport=Mock();transport.request.side_effect=lambda endpoint,**params:feed(endpoint)
    rt=TransitRuntime(service,transport=transport,clock=lambda:clock[0],utcnow=lambda:NOW)
    return service,rt,clock,transport


def test_one_poll_serves_same_stop_favorites_and_throttles_manual_refresh(tmp_path):
    service,rt,clock,transport=runtime(tmp_path)
    first=favorite(service,direction='N');favorite(service,direction='S')
    assert asyncio.run(rt.refresh(first['id']))
    assert len(service.transit.snapshot(NOW,private=False)[0]['departures'])==1
    assert service.transit.snapshot(NOW,private=False)[1]['departures']==[]
    assert not asyncio.run(rt.refresh(first['id']))
    assert transport.request.call_count==1
    clock[0]+=75
    assert asyncio.run(rt.refresh()) and transport.request.call_count==2


def test_no_calls_without_configuration_at_night_or_unknown_clock(tmp_path):
    service,rt,clock,transport=runtime(tmp_path)
    assert not asyncio.run(rt.refresh())
    favorite(service)
    for display in ({'mode':'night','awaiting_clock':False},{'mode':'day','awaiting_clock':True}):
        service.display_state=display
        assert not asyncio.run(rt.refresh())
    service.display_state=None;service.transit.set_token(None)
    assert not asyncio.run(rt.refresh())
    transport.request.assert_not_called()


def test_schedules_fallback_uses_next_slot_not_unbudgeted_immediate_retry(tmp_path):
    service,rt,clock,transport=runtime(tmp_path);favorite(service)
    transport.request.side_effect=lambda endpoint,**params:feed(endpoint,empty=endpoint=='StopMonitoring')
    asyncio.run(rt.refresh());assert transport.request.call_count==1
    clock[0]+=75;asyncio.run(rt.refresh())
    assert transport.request.call_args.args==('stoptimetable',)
    assert service.transit.snapshot(NOW,private=False)[0]['departures'][0]['kind']=='scheduled'


def test_failures_preserve_old_sample_mark_stale_and_backoff(tmp_path):
    service,rt,clock,transport=runtime(tmp_path);favorite(service)
    asyncio.run(rt.refresh());before=service.transit.items[0]['sample']['checked_at']
    clock[0]+=75;transport.request.side_effect=TransitUnavailable('provider failed')
    asyncio.run(rt.refresh());view=service.transit.snapshot(NOW,private=False)[0]
    assert view['state']=='stale' and view['checked_at']==before and view['departures']
    assert not asyncio.run(rt.refresh())
    clock[0]+=75;transport.request.side_effect=TransitQuota('limited');asyncio.run(rt.refresh())
    assert rt.next_request==clock[0]+3600


def test_preferred_group_does_not_starve_other_stops(tmp_path):
    service,rt,clock,transport=runtime(tmp_path)
    for i in range(6):favorite(service,stop_id=str(i),operator_name='Caltrain' if i==0 else 'Other')
    for i in range(16):asyncio.run(rt.refresh());clock[0]+=75
    assert {call.kwargs.get('stopcode',call.kwargs.get('monitoringref')) for call in transport.request.call_args_list}==set(map(str,range(6)))


def test_token_change_during_http_discards_response_and_serializes_requests(tmp_path):
    service,rt,clock,transport=runtime(tmp_path);item=favorite(service)
    entered=Event();release=Event()
    def blocked(*args,**kwargs):entered.set();release.wait(5);return feed()
    transport.request.side_effect=blocked
    async def check():
        job=asyncio.create_task(rt.refresh())
        await asyncio.to_thread(entered.wait,5)
        assert not await rt.refresh()
        service.transit.set_token(None);release.set();await job
    asyncio.run(check())
    assert service.transit.items[0]['sample'] is None


def directory_response(kind):
    if kind=='operators':return {'content':[{'Id':'OP','Name':'Agency','SiriOperatorRef':'RT','Monitored':True}]}
    if kind=='lines':return {'content':[{'Id':'route1','Name':'Express','SiriLineRef':'R','OperatorRef':'OP','Monitored':True}]}
    return {'Contents':{'dataObjects':{'ScheduledStopPoint':[{'id':'STOP','Name':'Station','Extensions':{'LocationType':'0'}},
        {'id':'PARENT','Name':'Parent','Extensions':{'LocationType':'1'}}]}}}


def test_discovery_cache_all_requests_share_real_budget_and_verify_mapping(tmp_path):
    storage=Storage(tmp_path/'luma.db');seen=[]
    def handler(request):seen.append(request);return httpx.Response(200,json=directory_response(request.url.path.split('/')[-1]))
    transport=TransitTransport(TransitBudget(storage),lambda:TOKEN,transport=httpx.MockTransport(handler))
    try:
        directory=TransitDirectory(storage,transport)
        verified=directory.verify(operator_id='OP',stop_id='STOP',route_id='route1')
        assert (verified['agency'],verified['line'])==('RT','R') and len(seen)==3
        directory.verify(operator_id='OP',stop_id='STOP',route_id='route1');assert len(seen)==3
        assert len(storage.get_cache('transit','budget'))==3
        directory.get('operators',force=True);assert len(storage.get_cache('transit','budget'))==4
        with pytest.raises(TransitUnavailable):directory.verify(operator_id='OP',stop_id='PARENT',route_id='route1')
    finally:transport.close()


def test_directory_storage_is_bounded_and_old_metadata_refetched(tmp_path):
    storage=Storage(tmp_path/'luma.db');transport=Mock();transport.request.side_effect=lambda kind,**params:directory_response(kind)
    directory=TransitDirectory(storage,transport)
    for i in range(15):directory.get('stops',operator_id=str(i),now=NOW+timedelta(seconds=i))
    with storage.connect() as connection:assert connection.execute("SELECT count(*) FROM cache WHERE namespace='transit_directory'").fetchone()[0]==12
    directory.get('stops',operator_id='14',now=NOW+timedelta(days=8));assert transport.request.call_count==16


def test_setup_preview_observed_directions_shares_poll_cooldown(tmp_path):
    service,rt,clock,transport=runtime(tmp_path)
    transport.request.side_effect=lambda kind,**params:feed(kind) if kind in ('StopMonitoring','stoptimetable') else directory_response(kind)
    result=asyncio.run(rt.preview(operator_id='OP',stop_id='STOP',route_id='route1'))
    assert result['directions']==['N'] and len(result['departures'])==1
    with pytest.raises(TransitQuota):asyncio.run(rt.preview(operator_id='OP',stop_id='STOP',route_id='route1'))
    favorite(service);assert not asyncio.run(rt.refresh())
    assert len([call for call in transport.request.call_args_list if call.args[0]=='StopMonitoring'])==1


def test_provider_failure_or_malformed_delivery_is_not_empty_success():
    assert delivery_ok(feed(empty=True),'StopMonitoring')
    assert not delivery_ok({'Siri':{'ServiceDelivery':{'StopMonitoringDelivery':{}}}},'StopMonitoring')
    data=feed();data['Siri']['ServiceDelivery']['Status']=False
    assert not delivery_ok(data,'StopMonitoring')


def test_public_favorite_redacted_at_night_and_private_data_after_lock(tmp_path):
    service,rt,clock,transport=runtime(tmp_path)
    favorite(service,public=True);favorite(service,stop_id='other',title='Private commute')
    service.unlock_with_pin();assert len(service.snapshot()['transit'])==2
    service.state.pin_unlocked_until=None;service.phone_disconnected();service.tick()
    assert [row['title'] for row in service.snapshot()['transit']]==['Station']
    service.display_clock_trusted=lambda:True
    service.update_settings({'onboarding_completed':True})
    service.state.forced_sleep_until=datetime.now(UTC)+timedelta(hours=1)
    assert service.snapshot()['transit']==[]


def test_api_secret_validation_owner_gates_privacy_and_verified_save(tmp_path):
    app=create_app(data_dir=tmp_path);client=TestClient(app);service=app.state.luma;rt=app.state.transit_runtime
    service.display_clock_trusted=lambda:True
    rt.transport.close();transport=Mock();transport.request.side_effect=lambda kind,**params:directory_response(kind)
    rt.transport=transport;rt.directory.transport=transport
    bad=client.post('/api/v1/transit/token',json={'token':TOKEN+' secret spaces'})
    assert bad.status_code==422 and TOKEN not in bad.text
    result=client.post('/api/v1/transit/token',json={'token':TOKEN})
    assert result.status_code==200 and result.json()['token_configured'] and TOKEN not in result.text
    response=client.post('/api/v1/transit/favorites',json={'title':'Commute','operator_id':'OP','stop_id':'STOP','route_id':'route1'})
    assert response.status_code==200
    saved=response.json()['items'][0]
    assert saved['agency']=='RT' and saved['line']=='R' and not saved['public']
    assert client.get('/api/v1/state').json()['transit']==[]
    remote=TestClient(app,client=('192.0.2.1',1234))
    token=app.state.security.get_or_create_lan_token()
    assert remote.get('/api/v1/transit',headers={'X-Luma-Token':token}).status_code==403
    service.update_settings({'onboarding_completed':True})
    assert client.get('/api/v1/transit').status_code==403
    assert client.post('/api/v1/transit/visible',json={'item_id':saved['id']}).status_code==403
    service.unlock_with_pin()
    assert client.post('/api/v1/security/pin',json={'pin':'123456'}).status_code==200
    assert client.get('/api/v1/state').json()['transit'][0]['title']=='Commute'
    assert client.post('/api/v1/transit/visible',json={'item_id':saved['id']}).status_code==200


def test_api_does_not_return_search_or_save_after_privacy_expires(tmp_path):
    app=create_app(data_dir=tmp_path);client=TestClient(app);service=app.state.luma;rt=app.state.transit_runtime
    service.display_clock_trusted=lambda:True
    service.update_settings({'onboarding_completed':True});service.unlock_with_pin()
    async def delayed(*args,**kwargs):
        service.state.pin_unlocked_until=None;service.phone_disconnected();service.tick()
        return [{'id':'private','name':'Private stop'}]
    rt.discover=delayed
    assert client.post('/api/v1/transit/directory',json={'kind':'operators'}).status_code==403
    rt.close()
