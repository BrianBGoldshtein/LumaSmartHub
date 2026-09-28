"""Bounded persisted dates and exact Google-event pins; no per-tick writes."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, date, datetime, time, timedelta
from math import ceil
import re
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


MAX_ITEMS = 12


def _title(value):
    if not isinstance(value,str) or not 1<=len(value.strip())<=100 or re.search(r'[\x00-\x1f\x7f]',value):
        raise ValueError('Use a title of 1 to 100 characters, without control characters.')
    return value.strip()


def manual_values(title, day, at, timezone, annual, public):
    title=_title(title)
    if type(annual) is not bool or type(public) is not bool:
        raise ValueError('Annual and public choices must be true or false.')
    try:
        if not isinstance(day,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day): raise ValueError()
        parsed=date.fromisoformat(day)
        if not 2000<=parsed.year<=2100: raise ValueError()
        zone=ZoneInfo(timezone)
        if at is not None:
            if not isinstance(at,str) or not re.fullmatch(r'\d{2}:\d{2}',at): raise ValueError()
            wall=datetime.combine(parsed,time.fromisoformat(at))
            target=wall.replace(tzinfo=zone,fold=0)
            if target.astimezone(UTC).astimezone(zone).replace(tzinfo=None)!=wall:
                raise ValueError('This local time is skipped by daylight saving. Choose another time.')
    except (ValueError,TypeError,ZoneInfoNotFoundError) as exc:
        raise ValueError('Choose a valid date (2000–2100), time and IANA timezone; skipped daylight-saving times are unavailable.') from exc
    return {'title':title,'date':day,'time':at,'timezone':timezone,'annual':annual,'public':public}


def _target(record, now):
    zone=ZoneInfo(record['timezone'])
    if record['source']=='google':
        return datetime.fromisoformat(record['start']).astimezone(zone)
    day=date.fromisoformat(record['date'])
    local=now.astimezone(zone)
    if record['annual']:
        original_day=day
        def anniversary(year):
            try: return original_day.replace(year=year)
            except ValueError: return date(year,2,28)  # February29 policy.
        day=anniversary(local.year)
        if day<local.date(): day=anniversary(local.year+1)
    at=time.fromisoformat(record['time']) if record['time'] else time.min
    target=datetime.combine(day,at,zone)
    # Future annual DST gaps are resolved forward by the size of the gap;
    # repeated hours consistently use their first occurrence (fold0).
    return target.astimezone(UTC).astimezone(zone)


def countdown_view(record, now):
    target=_target(record,now)
    local=now.astimezone(ZoneInfo(record['timezone']))
    days=(target.date()-local.date()).days
    timed=bool(record.get('time')) if record['source']=='manual' else not record['all_day']
    seconds=(target.astimezone(UTC)-now.astimezone(UTC)).total_seconds()
    state=record.get('state','ready')
    if record['source']=='google' and state=='ready':
        checked=datetime.fromisoformat(record['checked_at'])
        if not timedelta(0)<=now-checked<=timedelta(minutes=15): state='stale'
    if state in ('unavailable','deleted','unlinked'):
        label={'unavailable':'Unavailable','deleted':'Removed','unlinked':'Reconnect'}[state];value=None;unit=None
    elif days<0:
        label='Passed';value=None;unit=None
    elif timed and seconds<=0:
        label='Reached';value=None;unit=None
    elif timed and seconds<86400:
        value=max(1,ceil(seconds/3600));unit='hour' if value==1 else 'hours';label=f'{value} {unit}'
    elif days==0: label='Today';value=None;unit=None
    elif days==1: label='Tomorrow';value=None;unit=None
    else: value=days;unit='days';label=f'{days} days'
    return {'id':record['id'],'title':record['title'],'public':record['public'],'source':record['source'],
            'target':target.isoformat(),'date':target.date().isoformat(),'timed':timed,
            'label':label,'value':value,'unit':unit,'state':state,'past':days<0,
            'color':record.get('event_color') or record.get('calendar_color')}


class Countdowns:
    def __init__(self,storage):
        self.storage=storage
        raw=storage.get_cache('countdowns','items')
        self.items=[]
        self.recovery_error=False
        if raw is None: return
        try:
            if not isinstance(raw,dict) or raw.get('version')!=1 or not isinstance(raw.get('items'),list) or len(raw['items'])>MAX_ITEMS:
                raise ValueError()
            ids=set()
            for item in raw['items']:
                if item['id'] in ids or not re.fullmatch(r'[a-f0-9-]{36}',item['id']): raise ValueError()
                ids.add(item['id']);_title(item['title'])
                if type(item['public']) is not bool or not isinstance(item['revision'],str): raise ValueError()
                if item['source']=='manual':
                    manual_values(item['title'],item['date'],item['time'],item['timezone'],item['annual'],item['public'])
                elif item['source']=='google':
                    start=datetime.fromisoformat(item['start']);checked=datetime.fromisoformat(item['checked_at'])
                    ZoneInfo(item['timezone'])
                    if start.tzinfo is None or checked.tzinfo is None or type(item['all_day']) is not bool: raise ValueError()
                    if item['state'] not in ('ready','stale','deleted','unavailable','unlinked'): raise ValueError()
                    if not isinstance(item['calendar_id'],str) or not 1<=len(item['calendar_id'])<=1024 or not re.fullmatch(r'[A-Za-z0-9_]{1,1024}',item['event_id']): raise ValueError()
                    for key in ('calendar_color','event_color'):
                        if item.get(key) is not None and not re.fullmatch(r'#[a-fA-F0-9]{6}',item[key]): raise ValueError()
                else: raise ValueError()
                self.items.append(deepcopy(item))
        except (ValueError,TypeError,KeyError,ZoneInfoNotFoundError):
            # Keep the original DB record for recovery; never silently overwrite it.
            self.items=[];self.recovery_error=True

    def _save(self):
        self.storage.set_cache('countdowns','items',{'version':1,'items':self.items})

    def _editable(self):
        if self.recovery_error: raise ValueError('Saved countdowns need recovery; no existing data was overwritten.')

    def _replace(self,record,item_id=None,revision=None):
        self._editable()
        index=next((i for i,item in enumerate(self.items) if item['id']==item_id),None)
        if item_id is not None and (index is None or self.items[index]['revision']!=revision):
            raise ValueError('This countdown changed. Reload before editing.')
        if index is None and len(self.items)>=MAX_ITEMS: raise ValueError('Keep at most 12 countdowns.')
        record={**record,'id':item_id or str(uuid4()),'revision':str(uuid4())}
        previous=deepcopy(self.items)
        if index is None: self.items.append(record)
        else: self.items[index]=record
        try: self._save()
        except Exception:
            self.items=previous
            raise
        return deepcopy(record)

    def save_manual(self,*,title,day,at=None,timezone,annual=False,public=False,item_id=None,revision=None):
        values=manual_values(title,day,at,timezone,annual,public)
        return self._replace({'source':'manual',**values},item_id,revision)

    def pin_google(self,event,*,timezone,now,public=False):
        self._editable()
        if type(public) is not bool: raise ValueError('Choose public or private explicitly.')
        if event.status=='cancelled' or event.self_declined: raise ValueError('Choose an available, accepted event.')
        if any(item.get('calendar_id')==event.calendar_id and item.get('event_id')==event.id for item in self.items):
            raise ValueError('That event is already pinned.')
        ZoneInfo(timezone)
        return self._replace({'source':'google','calendar_id':event.calendar_id,'event_id':event.id,
                             'timezone':timezone,'public':public,**self._event_values(event,now)})

    @staticmethod
    def _event_values(event,now):
        title=re.sub(r'\s+',' ',re.sub(r'[\x00-\x1f\x7f]',' ',event.summary)).strip()[:100] or 'Untitled event'
        return {'title':title,'start':event.start.isoformat(),'all_day':event.all_day,
                'calendar_color':event.calendar_color,'event_color':event.event_color,'state':'ready','checked_at':now.isoformat()}

    def refresh(self,item_id,revision,*,event=None,state=None,now):
        self._editable()
        item=next((item for item in self.items if item['id']==item_id and item['revision']==revision and item['source']=='google'),None)
        if item is None: return False  # A slow provider response cannot recreate an unpinned/edited item.
        values=dict(item)
        if event is not None:
            if (event.calendar_id,event.id)!=(item['calendar_id'],item['event_id']): raise ValueError('Mismatched event response.')
            if event.status=='cancelled': state='deleted'
            elif event.self_declined: state='unavailable'
            else: values.update(self._event_values(event,now))
        if state:
            if state not in ('stale','deleted','unavailable','unlinked'): raise ValueError('Invalid pin state.')
            values['state']=state
        if values==item: return False
        self._replace(values,item_id,revision)
        return True

    def set_public(self,item_id,revision,public):
        if type(public) is not bool: raise ValueError('Public must be a boolean.')
        item=next((item for item in self.items if item['id']==item_id),None)
        if item is None: raise ValueError('Countdown not found.')
        return self._replace({**item,'public':public},item_id,revision)

    def remove(self,item_id,revision):
        self._editable()
        item=next((item for item in self.items if item['id']==item_id and item['revision']==revision),None)
        if item is None: raise ValueError('This countdown changed. Reload before removing it.')
        previous=list(self.items);self.items=[item for item in self.items if item['id']!=item_id]
        try: self._save()
        except Exception:
            self.items=previous
            raise

    def snapshot(self,now,*,private,quiet=False):
        if quiet: return []
        views=[countdown_view(item,now) for item in self.items if item['public'] or not private]
        return sorted([view for view in views if not view['past'] or view['state'] in ('deleted','unavailable','unlinked')],key=lambda view:(view['target'],view['id']))

    def configuration(self,now):
        return {'items':deepcopy(self.items),'views':[countdown_view(item,now) for item in self.items],
                'limit':MAX_ITEMS,'recovery_error':self.recovery_error}
