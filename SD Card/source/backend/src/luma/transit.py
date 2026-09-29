"""Six durable transit favorites. No per-tick writes or credentials in views."""
from copy import deepcopy
from datetime import UTC,datetime,timedelta
from math import ceil
import json
import re
from threading import RLock
from uuid import UUID,uuid4

from .transit_metadata import identifier
from .transit_parser import instant


def label(value):
    if not isinstance(value,str) or not 1<=len(value.strip())<=100 or re.search(r'[\x00-\x1f\x7f]',value):
        raise ValueError('Use a transit label of 1 to 100 characters without control characters.')
    return value.strip()


def favorite_values(*,title,operator_id,operator_name,agency,stop_id,stop_name,route_id=None,
                    line=None,direction=None,monitored=False,public=False):
    if type(public) is not bool or type(monitored) is not bool:raise ValueError('Choose transit visibility explicitly.')
    if bool(route_id)!=bool(line):raise ValueError('Select a complete route or all routes.')
    return {'title':label(title),'operator_id':identifier(operator_id),'operator_name':label(operator_name),
            'agency':identifier(agency),'stop_id':identifier(stop_id),'stop_name':label(stop_name),
            'route_id':identifier(route_id) if route_id is not None else None,
            'line':identifier(line) if line is not None else None,
            'direction':identifier(direction) if direction is not None else None,
            'monitored':monitored,'public':public}


def validate_sample(sample):
    if sample is None:return
    if not isinstance(sample,dict) or instant(sample.get('checked_at')) is None or type(sample.get('failed')) is not bool:
        raise ValueError('Invalid saved transit sample.')
    rows=sample.get('departures')
    if not isinstance(rows,list) or len(rows)>60:raise ValueError('Invalid saved transit departures.')
    for row in rows:
        if not isinstance(row,dict) or row.get('kind') not in ('predicted','scheduled') or instant(row.get('at')) is None:
            raise ValueError('Invalid saved transit departure.')
        for key in ('route_id','route','direction','destination'):
            if not isinstance(row.get(key),str) or len(row[key])>160:raise ValueError('Invalid saved transit label.')
        for key in ('updated_at','scheduled_at','prediction_until'):
            if row.get(key) is not None and instant(row[key]) is None:raise ValueError('Invalid saved transit time.')
        if row['kind']=='predicted' and instant(row.get('prediction_until')) is None:raise ValueError('Prediction has no expiry.')


def departure_view(row,now,checked_at,failed=False):
    at=instant(row['at'])
    # An already-passed expected departure cannot reappear as a later schedule.
    if at is None or at<now:return None
    prediction_until=instant(row.get('prediction_until'))
    cache_fresh=timedelta(0)<=now-checked_at<=timedelta(minutes=5)
    predicted=bool(row['kind']=='predicted' and prediction_until and now<=prediction_until and cache_fresh)
    if row['kind']=='predicted' and not predicted:at=instant(row.get('scheduled_at'))
    if at is None or not now<=at<=now+timedelta(days=1):return None
    return {'route':row['route'],'direction':row['direction'],'destination':row['destination'],
            'at':at.isoformat(),'minutes':ceil((at-now).total_seconds()/60),
            'kind':'predicted' if predicted else 'scheduled','stale':failed or not cache_fresh,
            'updated_at':row.get('updated_at'),'scheduled_at':row.get('scheduled_at'),
            'prediction_until':row.get('prediction_until') if predicted else None}


class Transit:
    """Single application owner, serialized mutations with durable rollback."""
    def __init__(self,storage):
        self.storage=storage;self.lock=RLock();self._items=[];self.recovery_error=False
        self.generation=str(uuid4())  # A new process invalidates no live old-process jobs.
        try:
            raw=storage.get_cache('transit','favorites')
            if raw is None:return
            if not isinstance(raw,dict) or raw.get('version')!=1 or not isinstance(raw.get('items'),list) or len(raw['items'])>6:raise ValueError()
            seen=set()
            for item in raw['items']:
                if str(UUID(item['id']))!=item['id'] or str(UUID(item['revision']))!=item['revision'] or item['id'] in seen:raise ValueError()
                seen.add(item['id'])
                keys=('title','operator_id','operator_name','agency','stop_id','stop_name','route_id','line','direction','monitored','public')
                clean=favorite_values(**{key:item[key] for key in keys})
                validate_sample(item.get('sample'))
                self._items.append({**clean,'id':item['id'],'revision':item['revision'],'sample':deepcopy(item.get('sample'))})
        except (ValueError,TypeError,KeyError,AttributeError):
            self._items=[];self.recovery_error=True  # Preserve original corrupt record, never overwrite it.

    @property
    def items(self):
        with self.lock:return deepcopy(self._items)

    def token(self):
        value=self.storage.get_secret('transit.511')
        return value if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_-]{16,256}',value) else None

    def set_token(self,value):
        if value is not None and (not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,256}',value)):
            raise ValueError('Use the token issued by 511, without spaces.')
        with self.lock:
            self._editable()
            changed=[{**item,'sample':None} for item in self._items]
            with self.storage.transaction() as connection:
                if value is None:connection.execute("DELETE FROM secrets WHERE key='transit.511'")
                else:connection.execute("INSERT INTO secrets(key,payload,updated_at) VALUES('transit.511',?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",(value,datetime.now(UTC).isoformat()))
                self._write(connection,changed)
            self._items=changed;self.generation=str(uuid4())
            # The request budget is deliberately NOT cleared when switching tokens.

    def _editable(self):
        if self.recovery_error:raise ValueError('Saved transit favorites need recovery; nothing was overwritten.')

    @staticmethod
    def _write(connection,items):
        connection.execute("INSERT INTO cache(namespace,key,payload,updated_at) VALUES('transit','favorites',?,?) ON CONFLICT(namespace,key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
                           (json.dumps({'version':1,'items':items}),datetime.now(UTC).isoformat()))

    def _commit(self,items):
        self._editable()
        with self.storage.transaction() as connection:self._write(connection,items)
        self._items=items

    def save(self,*,item_id=None,revision=None,**values):
        clean=favorite_values(**values)
        with self.lock:
            self._editable();items=self.items
            index=next((i for i,item in enumerate(items) if item['id']==item_id),None)
            if item_id is not None and (index is None or items[index]['revision']!=revision):raise ValueError('This transit favorite changed. Reload before editing.')
            if index is None and len(items)>=6:raise ValueError('Keep at most six transit favorites.')
            identity=lambda item:(item['operator_id'],item['stop_id'],item['route_id'],item['direction'])
            if any(item['id']!=item_id and identity(item)==identity(clean) for item in items):raise ValueError('That stop and direction are already saved.')
            record={**clean,'id':item_id or str(uuid4()),'revision':str(uuid4()),'sample':None}
            if index is None:items.append(record)
            else:
                # Cosmetic/visibility edits retain data but invalidate pending responses.
                if all(items[index][key]==record[key] for key in ('agency','stop_id','line','direction','monitored')):record['sample']=items[index]['sample']
                items[index]=record
            self._commit(items);return deepcopy(record)

    def remove(self,item_id,revision):
        with self.lock:
            if not any(item['id']==item_id and item['revision']==revision for item in self._items):raise ValueError('This transit favorite changed. Reload before removing it.')
            self._commit([item for item in self._items if item['id']!=item_id])

    def update(self,item_id,revision,generation,*,departures=None,failed=False,now):
        with self.lock:
            if generation!=self.generation:return False
            items=self.items;index=next((i for i,item in enumerate(items) if item['id']==item_id and item['revision']==revision),None)
            if index is None:return False
            previous=items[index]['sample']
            if failed:
                sample={**previous,'failed':True} if previous else {'checked_at':now.isoformat(),'failed':True,'departures':[]}
            else:sample={'checked_at':now.isoformat(),'failed':False,'departures':deepcopy(departures or [])[:60]}
            validate_sample(sample)
            if sample==previous:return False
            items[index]['sample']=sample;self._commit(items);return True

    def snapshot(self,now,*,private,quiet=False):
        if quiet:return []
        result=[]
        for item in self.items:
            if private and not item['public']:continue
            sample=item.get('sample');checked=instant(sample.get('checked_at')) if sample else None
            rows=[view for row in sample['departures'] if (view:=departure_view(row,now,checked,sample['failed']))] if sample and checked and now>=checked else []
            rows.sort(key=lambda row:(row['at'],row['route'],row['destination']))
            stale=not checked or not timedelta(0)<=now-checked<=timedelta(minutes=5) or bool(sample and sample['failed'])
            result.append({'id':item['id'],'title':item['title'],'operator':item['operator_name'],'stop':item['stop_name'],
                           'direction':item['direction'],'public':item['public'],'departures':rows[:3],
                           'state':'stale' if rows and stale else 'ready' if rows else 'unavailable' if stale else 'empty',
                           'checked_at':checked.isoformat() if checked else None})
        return result

    def configuration(self,now):
        return {'items':[{k:v for k,v in item.items() if k!='sample'} for item in self.items],
                'views':self.snapshot(now,private=False),'token_configured':bool(self.token()),'recovery_error':self.recovery_error}
