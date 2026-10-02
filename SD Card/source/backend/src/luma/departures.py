"""Opt-in local departure reminders; no route estimates or Google writes."""
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json

from .models import CalendarEvent, Settings


def occurrence_key(event: CalendarEvent) -> str:
    return sha256(json.dumps([event.calendar_id,event.id,event.start.astimezone(UTC).isoformat(),event.end.astimezone(UTC).isoformat()],separators=(',',':')).encode()).hexdigest()


def eligible(event: CalendarEvent, settings: Settings, now: datetime) -> bool:
    return (event.calendar_id in settings.departure_calendar_ids and event.status != 'cancelled'
            and not event.all_day and not event.self_declined and event.start.astimezone(UTC) > now.astimezone(UTC)
            and event.summary.strip().casefold() != settings.sleep_event_title.strip().casefold()
            and (settings.departure_include_virtual or not event.virtual_only))


def _minutes(value):
    return type(value) is int and 0 <= value <= 240


class Departures:
    def __init__(self, storage):
        self.storage = storage
        self.records = {}
        raw = storage.get_cache('departures','occurrences')
        if isinstance(raw, dict):
            for key, value in list(raw.items())[-256:]:
                if not isinstance(key,str) or len(key)!=64 or any(c not in '0123456789abcdef' for c in key) or not isinstance(value,dict):
                    continue
                try:
                    expiry = datetime.fromisoformat(value['expires'])
                    snooze = datetime.fromisoformat(value['snooze_until']) if value.get('snooze_until') else None
                    if expiry.tzinfo is None or (snooze and snooze.tzinfo is None):
                        continue
                    record = {'expires':expiry.astimezone(UTC).isoformat(),'dismissed':value.get('dismissed') is True}
                    if value.get('chimed') is True: record['chimed'] = True
                    if snooze: record['snooze_until'] = min(snooze,expiry).astimezone(UTC).isoformat()
                    if _minutes(value.get('prep')) and _minutes(value.get('travel')):
                        record.update(prep=value['prep'],travel=value['travel'])
                    self.records[key] = record
                except (KeyError,ValueError,TypeError):
                    continue

    def snapshot(self, events, settings, now, *, private=False, fresh=True):
        if private or not fresh or not settings.departure_enabled:
            return None
        now = now.astimezone(UTC)
        candidates = []
        for event in events:
            if not eligible(event,settings,now):
                continue
            key = occurrence_key(event)
            record = self.records.get(key,{})
            if record.get('dismissed') or (record.get('snooze_until') and datetime.fromisoformat(record['snooze_until']) > now):
                continue
            prep = record.get('prep',settings.departure_prep_minutes)
            travel = record.get('travel',settings.departure_travel_minutes)
            departure = event.start.astimezone(UTC) - timedelta(minutes=prep+travel)
            if departure-timedelta(minutes=15) <= now < event.start.astimezone(UTC):
                candidates.append({'key':key,'title':event.summary,'start':event.start.isoformat(),
                                   'depart_at':departure.isoformat(),'prep_minutes':prep,'travel_minutes':travel,
                                   'color':event.event_color or event.calendar_color})
        return min(candidates,key=lambda item:(item['depart_at'],item['start'],item['key'])) if candidates else None

    def claim_chime(self, reminder, now):
        """Persist an at-most-once cue claim for a displayed occurrence.

        Claiming before playback deliberately avoids replay after a bridge
        restart, failed speaker route, snooze, or a calendar refresh.
        """
        if not reminder or not isinstance(reminder.get('key'), str):
            return False
        key = reminder['key']
        if self.records.get(key, {}).get('chimed'):
            return False
        expiry = datetime.fromisoformat(reminder['start']).astimezone(UTC)
        if expiry <= now.astimezone(UTC):
            return False
        record = dict(self.records.get(key, {}))
        record.update(expires=expiry.isoformat(), chimed=True)
        retained = {k: v for k, v in self.records.items()
                    if datetime.fromisoformat(v['expires']) > now.astimezone(UTC)}
        retained.pop(key, None)
        retained = dict(sorted(retained.items(), key=lambda item: item[1]['expires'])[:255])
        retained[key] = record
        self.storage.set_cache('departures', 'occurrences', retained)
        self.records = retained
        return True

    def act(self, *, key, action, events, settings, now, prep=None, travel=None):
        if action not in {'snooze','dismiss','override'}:
            raise ValueError('Unsupported reminder action')
        if action == 'override':
            if not _minutes(prep) or not _minutes(travel):
                raise ValueError('Use whole minutes from 0 to 240')
        elif prep is not None or travel is not None:
            raise ValueError('Unexpected reminder fields')
        event = next((event for event in events if occurrence_key(event)==key and eligible(event,settings,now)),None)
        if event is None or not settings.departure_enabled:
            raise ValueError('This event changed or is no longer eligible. Refresh the calendar.')
        record = dict(self.records.get(key,{}))
        record['expires'] = event.start.astimezone(UTC).isoformat()
        if action=='dismiss':record['dismissed']=True
        elif action=='snooze':record['snooze_until']=min(now+timedelta(minutes=5),event.start).astimezone(UTC).isoformat()
        else:record.update(prep=prep,travel=travel)
        retained={k:v for k,v in self.records.items() if datetime.fromisoformat(v['expires']) > now}
        retained.pop(key,None)
        # Always retain the action just confirmed to the owner. Bound storage;
        # expiry pruning happens on actions, never every tick.
        retained=dict(sorted(retained.items(),key=lambda item:item[1]['expires'])[:255])
        retained[key]=record
        self.storage.set_cache('departures','occurrences',retained)
        self.records=retained
