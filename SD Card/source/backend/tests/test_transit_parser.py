from datetime import UTC,datetime,timedelta
from copy import deepcopy

import pytest

from luma.transit_parser import parse_departures

NOW=datetime(2026,9,26,20,tzinfo=UTC)


def stamp(minutes):return (NOW+timedelta(minutes=minutes)).isoformat()


def payload(*,monitored=True,recorded=-1,response=-1,expected=6,scheduled=8):
    return {'Siri':{'ServiceDelivery':{'ResponseTimestamp':stamp(response),'Status':True,
        'StopMonitoringDelivery':{'MonitoredStopVisit':{'RecordedAtTime':stamp(recorded),'MonitoringRef':'STOP',
            'MonitoredVehicleJourney':{'LineRef':'route','PublishedLineName':'Express','DirectionRef':'N',
                'DestinationName':'Campus','Monitored':monitored,'FramedVehicleJourneyRef':{'DatedVehicleJourneyRef':'trip'},
                'MonitoredCall':{'StopPointRef':'STOP','ExpectedDepartureTime':stamp(expected),'AimedDepartureTime':stamp(scheduled)}}}}}}}


def test_predicted_requires_fresh_vehicle_and_response_timestamps():
    result=parse_departures(payload(),stop='STOP',now=NOW)
    assert result[0]['kind']=='predicted' and result[0]['minutes']==6
    assert result[0]['destination']=='Campus'


@pytest.mark.parametrize('changes',[{'monitored':False},{'recorded':-6},{'response':-6},{'recorded':1},{'response':1}])
def test_stale_unmonitored_or_future_updates_use_schedule_never_live(changes):
    result=parse_departures(payload(**changes),stop='STOP',now=NOW)
    assert result[0]['kind']=='scheduled' and result[0]['minutes']==8


def test_stale_prediction_without_future_schedule_is_unavailable():
    assert parse_departures(payload(recorded=-6,scheduled=-1),stop='STOP',now=NOW)==[]
    assert parse_departures(payload(expected=-1),stop='STOP',now=NOW)==[]


def test_stop_direction_and_route_filters_do_not_mix_platforms():
    data=payload()
    assert parse_departures(data,stop='OTHER',now=NOW)==[]
    assert parse_departures(data,stop='STOP',direction='S',now=NOW)==[]
    assert parse_departures(data,stop='STOP',route='other',now=NOW)==[]
    assert len(parse_departures(data,stop='STOP',direction='N',route='route',now=NOW))==1


def test_schedule_delivery_list_and_singleton_forms_deduplicate():
    data=payload();service=data['Siri']['ServiceDelivery'];journey=deepcopy(service['StopMonitoringDelivery']['MonitoredStopVisit']['MonitoredVehicleJourney'])
    journey['TargetedCall']=journey.pop('MonitoredCall')
    service['StopTimetableDelivery']=[{'TimetabledStopVisit':[{'TargetedVehicleJourney':journey}]*2}]
    assert len(parse_departures(data,stop='STOP',now=NOW))==1
    service.pop('StopMonitoringDelivery')
    result=parse_departures(data,stop='STOP',now=NOW)
    assert len(result)==1 and result[0]['kind']=='scheduled'


@pytest.mark.parametrize('change',[{'DepartureStatus':'cancelled'},{'ActualDepartureTime':stamp(-1)},
                                 {'ExpectedDepartureTime':'broken','AimedDepartureTime':'2026-09-26T20:08:00'}])
def test_cancelled_departed_or_timezone_naive_rows_not_displayed(change):
    data=payload();data['Siri']['ServiceDelivery']['StopMonitoringDelivery']['MonitoredStopVisit']['MonitoredVehicleJourney']['MonitoredCall'].update(change)
    assert parse_departures(data,stop='STOP',now=NOW)==[]


def test_provider_failure_empty_and_partial_records_are_safe():
    data=payload();data['Siri']['ServiceDelivery']['Status']=False
    assert parse_departures(data,stop='STOP',now=NOW)==[]
    for data in ({},[],None,{'Siri':None},{'Siri':[]},{'Siri':{'ServiceDelivery':None}},
                 {'Siri':{'ServiceDelivery':{'StopMonitoringDelivery':[None,{},'bad']}}},
                 {'Siri':{'ServiceDelivery':{'StopMonitoringDelivery':{'MonitoredStopVisit':[{},None]}}}}):
        assert parse_departures(data,stop='STOP',now=NOW)==[]


def test_malformed_siblings_do_not_hide_valid_departures():
    data=payload();service=data['Siri']['ServiceDelivery'];delivery=service['StopMonitoringDelivery']
    visit=delivery['MonitoredStopVisit']
    delivery['MonitoredStopVisit']=[None,[],42,{'MonitoredVehicleJourney':None},
                                   {'MonitoredVehicleJourney':{'MonitoredCall':None}},visit]
    service['StopMonitoringDelivery']=[None,'bad',delivery]
    result=parse_departures(data,stop='STOP',now=NOW)
    assert len(result)==1 and result[0]['minutes']==6
