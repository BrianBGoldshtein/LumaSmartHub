from copy import deepcopy
from datetime import UTC,datetime,timedelta
from unittest.mock import Mock

import pytest

from luma.storage import Storage
from luma.transit import Transit
from luma.transit_metadata import parse_metadata
from luma.transit_parser import parse_departures
from luma.transit_transport import TransitUnavailable

NOW=datetime(2026,9,26,20,tzinfo=UTC)


def favorite(transit,**changes):
    return transit.save(**{'title':'To campus','operator_id':'OP','operator_name':'Test Transit','agency':'RT',
                          'stop_id':'STOP','stop_name':'Station','monitored':True,**changes})


def departure(**changes):
    return {'route_id':'R','route':'Express','direction':'N','destination':'Campus',
            'at':(NOW+timedelta(minutes=10)).isoformat(),'minutes':10,'kind':'predicted',
            'updated_at':NOW.isoformat(),'prediction_until':(NOW+timedelta(minutes=5)).isoformat(),
            'scheduled_at':(NOW+timedelta(minutes=12)).isoformat(),**changes}


def test_favorites_persist_private_default_revision_and_bound(tmp_path):
    storage=Storage(tmp_path/'luma.db');transit=Transit(storage);item=favorite(transit)
    assert transit.snapshot(NOW,private=True)==[]
    assert Transit(storage).items==transit.items
    edited=favorite(transit,item_id=item['id'],revision=item['revision'],public=True)
    assert transit.snapshot(NOW,private=True)[0]['title']=='To campus'
    assert transit.snapshot(NOW,private=False,quiet=True)==[]
    with pytest.raises(ValueError,match='changed'):transit.remove(item['id'],item['revision'])
    with pytest.raises(ValueError,match='already saved'):favorite(transit)
    for i in range(5):favorite(transit,stop_id=str(i))
    with pytest.raises(ValueError,match='six'):favorite(transit,stop_id='seventh')
    transit.remove(edited['id'],edited['revision']);assert len(Transit(storage).items)==5


@pytest.mark.parametrize('change',[{'title':''},{'title':'\nsecret'},{'public':1},{'direction':''},
                                   {'stop_id':'x\x00'},{'operator_id':None},{'route_id':'r'},{'monitored':'yes'}])
def test_invalid_favorites_do_not_write(tmp_path,change):
    transit=Transit(Storage(tmp_path/'luma.db'))
    with pytest.raises(ValueError):favorite(transit,**change)
    assert transit.items==[]


def test_staleness_ages_at_read_time_and_does_not_resurrect_departed_vehicle(tmp_path):
    transit=Transit(Storage(tmp_path/'luma.db'));item=favorite(transit)
    transit.update(item['id'],item['revision'],transit.generation,departures=[departure()],now=NOW)
    view=lambda minute:transit.snapshot(NOW+timedelta(minutes=minute),private=False)[0]
    assert view(1)['departures'][0]['minutes']==9
    assert view(1)['departures'][0]['kind']=='predicted'
    assert view(6)['departures'][0]['kind']=='scheduled' and view(6)['departures'][0]['minutes']==6
    assert view(6)['state']=='stale'
    assert view(11)['departures']==[]  # Don't resurrect at its later scheduled time.
    assert view(-1)['departures']==[]  # Clock rollback.
    transit.storage.transaction=Mock(side_effect=AssertionError('No writes from snapshots'))
    for i in range(100):view(i)


def test_disk_failure_rolls_back_and_slow_response_cannot_recreate_or_retarget(tmp_path):
    transit=Transit(Storage(tmp_path/'luma.db'));item=favorite(transit);generation=transit.generation
    original=transit.storage.transaction
    transit.storage.transaction=Mock(side_effect=OSError('full'))
    with pytest.raises(OSError):favorite(transit,stop_id='new')
    assert len(transit.items)==1
    transit.storage.transaction=original
    changed=favorite(transit,item_id=item['id'],revision=item['revision'],public=True)
    assert not transit.update(item['id'],item['revision'],generation,departures=[departure()],now=NOW)
    transit.remove(changed['id'],changed['revision'])
    assert not transit.update(changed['id'],changed['revision'],generation,departures=[departure()],now=NOW)


def test_token_never_in_configuration_and_changing_it_preserves_quota(tmp_path):
    storage=Storage(tmp_path/'luma.db');transit=Transit(storage);item=favorite(transit);old=transit.generation
    storage.set_cache('transit','budget',[NOW.timestamp()])
    token='synthetic-test-token-no-account'
    transit.set_token(token)
    assert transit.token()==token and transit.configuration(NOW)['token_configured']
    assert token not in str(transit.configuration(NOW)) and token not in str(transit.snapshot(NOW,private=False))
    assert not transit.update(item['id'],item['revision'],old,departures=[departure()],now=NOW)
    transit.set_token(None)
    assert transit.token() is None and len(transit.items)==1 and transit.items[0]['sample'] is None
    assert storage.get_cache('transit','budget')==[NOW.timestamp()]


def test_token_and_sample_reset_are_one_transaction(tmp_path):
    transit=Transit(Storage(tmp_path/'luma.db'));favorite(transit);transit.set_token('synthetic_original_token')
    generation=transit.generation
    transit._write=Mock(side_effect=OSError('full'))
    with pytest.raises(OSError):transit.set_token('synthetic_replacement_token')
    assert transit.token()=='synthetic_original_token' and transit.generation==generation


@pytest.mark.parametrize('raw',[{},[],{'version':1,'items':[None]}, {'version':1,'items':[{'id':'broken'}]}])
def test_corrupt_store_preserved(tmp_path,raw):
    storage=Storage(tmp_path/'luma.db');storage.set_cache('transit','favorites',raw)
    transit=Transit(storage)
    assert transit.recovery_error and transit.items==[]
    with pytest.raises(ValueError,match='recovery'):favorite(transit)
    assert storage.get_cache('transit','favorites')==raw


def test_real_documented_metadata_json_shapes_and_distinct_realtime_ids():
    operator=parse_metadata('operators',{'content':[{'Id':'OP','Name':'Agency','SiriOperatorRef':'RT','Monitored':True},None]})[0]
    line=parse_metadata('lines',{'content':{'Id':'OP:route / one','Name':'Express','SiriLineRef':'42','OperatorRef':'OP','Monitored':'true'}})[0]
    stop=parse_metadata('stops',{'Contents':{'dataObjects':{'ScheduledStopPoint':{'id':'STOP','Name':'Station','Extensions':{'PlatformCode':'2','LocationType':'0'}}}}})[0]
    assert operator['realtime_id']=='RT' and line['realtime_id']=='42' and line['id']=='OP:route / one'
    assert stop['platform']=='2' and not stop['station']
    assert parse_metadata('operators',[])==[]
    with pytest.raises(TransitUnavailable):parse_metadata('stops',{'content':[]})
    with pytest.raises(TransitUnavailable):parse_metadata('operators',[{}]*501)


def test_cancellation_list_item_and_trip_filters():
    journey={'LineRef':'R','DirectionRef':'N','Monitored':True,'FramedVehicleJourneyRef':{'DatedVehicleJourneyRef':'trip'},
             'MonitoredCall':{'StopPointRef':'STOP','VisitNumber':'1','ExpectedDepartureTime':departure()['at']}}
    visit={'ItemIdentifier':'item','RecordedAtTime':NOW.isoformat(),'MonitoredVehicleJourney':journey}
    delivery={'ResponseTimestamp':NOW.isoformat(),'MonitoredStopVisit':visit}
    payload={'Siri':{'ServiceDelivery':{'StopMonitoringDelivery':delivery}}}
    for cancellation in ({'ItemRef':'item'}, {'MonitoringRef':'STOP','VisitNumber':1,'LineRef':'R','DirectionRef':'N','VehicleJourneyRef':{'DatedVehicleJourneyRef':'trip'}}):
        delivery['MonitoredStopVisitCancellation']=[None,cancellation]
        assert parse_departures(payload,stop='STOP',now=NOW)==[]
    cancellation['DirectionRef']='S'
    assert len(parse_departures(payload,stop='STOP',now=NOW))==1
