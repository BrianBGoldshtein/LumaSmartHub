"""Minimal SIRI departures. Never turn an old prediction into a live ETA."""
from datetime import UTC, datetime, timedelta
from math import ceil


def items(value):
    return [item for item in value if isinstance(item,dict)] if isinstance(value,list) else [value] if isinstance(value,dict) else []


def text(value,limit=160):
    if isinstance(value,dict):value=value.get('value',value.get('Value',''))
    return ''.join(c for c in str(value or '') if ord(c)>=32)[:limit]


def instant(value):
    try:
        parsed=datetime.fromisoformat(text(value).replace('Z','+00:00'))
        return parsed.astimezone(UTC) if parsed.tzinfo else None
    except (ValueError,TypeError):return None


def boolean(value):return value is True or value=='true'


def cancelled(visit,journey,call,cancellations):
    for cancellation in cancellations:
        item=text(cancellation.get('ItemRef')).strip()
        if item and item==text(visit.get('ItemIdentifier')).strip():return True
        ref=cancellation.get('VehicleJourneyRef')
        ref=ref if isinstance(ref,dict) else {}
        trip=text(ref.get('DatedVehicleJourneyRef')).strip()
        journey_ref=journey.get('FramedVehicleJourneyRef')
        journey_ref=journey_ref if isinstance(journey_ref,dict) else {}
        journey_trip=text(journey.get('DatedVehicleJourneyRef') or journey_ref.get('DatedVehicleJourneyRef')).strip()
        if not trip or trip!=journey_trip:continue
        # A trip-level cancellation still has to identify this stop/visit.
        stop=text(cancellation.get('MonitoringRef')).strip()
        if not stop or stop!=text(call.get('StopPointRef') or visit.get('MonitoringRef')).strip():continue
        filters=((cancellation.get('LineRef'),journey.get('LineRef')),
                 (cancellation.get('DirectionRef'),journey.get('DirectionRef')),
                 (cancellation.get('VisitNumber'),call.get('VisitNumber')),
                 (ref.get('DataFrameRef'),journey_ref.get('DataFrameRef')))
        if all(not text(want) or text(want).strip()==text(actual).strip() for want,actual in filters):return True
    return False


def parse_departures(payload,*,stop,direction=None,route=None,now=None):
    now=(now or datetime.now(UTC)).astimezone(UTC)
    siri=payload.get('Siri') if isinstance(payload,dict) else None
    service=siri.get('ServiceDelivery',{}) if isinstance(siri,dict) else {}
    if not isinstance(service,dict) or service.get('Status') in (False,'false'):return []
    cancellations=[entry for delivery in items(service.get('StopMonitoringDelivery'))
                   for entry in items(delivery.get('MonitoredStopVisitCancellation'))]
    results={}
    for key,visits_key,journey_key,call_key in (
        ('StopMonitoringDelivery','MonitoredStopVisit','MonitoredVehicleJourney','MonitoredCall'),
        ('StopTimetableDelivery','TimetabledStopVisit','TargetedVehicleJourney','TargetedCall')):
        for delivery in items(service.get(key)):
            if delivery.get('Status') in (False,'false'):continue
            response_at=instant(delivery.get('ResponseTimestamp') or service.get('ResponseTimestamp'))
            for visit in items(delivery.get(visits_key)):
                journey=visit.get(journey_key,{})
                if not isinstance(journey,dict):continue
                call=journey.get(call_key,{})
                if not isinstance(call,dict):continue
                if cancelled(visit,journey,call,cancellations):continue
                if text(call.get('StopPointRef') or visit.get('MonitoringRef'))!=str(stop):continue
                if direction is not None and text(journey.get('DirectionRef'))!=str(direction):continue
                if route is not None and text(journey.get('LineRef'))!=str(route):continue
                if text(call.get('DepartureStatus')).lower() in ('cancelled','canceled') or call.get('ActualDepartureTime'):continue
                recorded=instant(visit.get('RecordedAtTime'))
                fresh=all(value and timedelta(0)<=now-value<=timedelta(minutes=5) for value in (recorded,response_at))
                predicted=instant(call.get('ExpectedDepartureTime') or call.get('ExpectedArrivalTime'))
                scheduled=instant(call.get('AimedDepartureTime') or call.get('AimedArrivalTime'))
                live=bool(key=='StopMonitoringDelivery' and boolean(journey.get('Monitored')) and fresh and predicted)
                departure=predicted if live else scheduled
                if departure is None or not now<=departure<=now+timedelta(days=1):continue
                route_id=text(journey.get('LineRef'))
                ref=journey.get('FramedVehicleJourneyRef') or {}
                trip=text(journey.get('DatedVehicleJourneyRef') or (ref.get('DatedVehicleJourneyRef') if isinstance(ref,dict) else ''))
                identity=(route_id,text(journey.get('DirectionRef')),trip or departure.isoformat(),scheduled.isoformat() if scheduled else '')
                result={'route_id':route_id,'route':text(journey.get('PublishedLineName') or route_id,40),
                        'direction':text(journey.get('DirectionRef'),80),'destination':text(journey.get('DestinationName')),
                        'at':departure.isoformat(),'minutes':ceil((departure-now).total_seconds()/60),
                        'kind':'predicted' if live else 'scheduled','updated_at':recorded.isoformat() if recorded else None,
                        'scheduled_at':scheduled.isoformat() if scheduled else None,
                        'prediction_until':(min(recorded,response_at)+timedelta(minutes=5)).isoformat() if live else None}
                if identity not in results or live:results[identity]=result
    return sorted(results.values(),key=lambda row:(row['at'],row['route'],row['destination']))
