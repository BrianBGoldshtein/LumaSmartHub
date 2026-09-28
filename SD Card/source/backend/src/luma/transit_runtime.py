"""Serialized quota-aware discovery and polling. Every request uses one transport."""
import asyncio
from datetime import UTC,datetime,timedelta
from hashlib import sha256
import json
from time import monotonic

from .transit_metadata import identifier,parse_metadata
from .transit_parser import instant,items,parse_departures
from .transit_transport import TransitBudget,TransitTransport,TransitUnavailable,TransitQuota


class TransitDirectory:
    def __init__(self,storage,transport):self.storage,self.transport=storage,transport

    def get(self,kind,*,operator_id=None,line_id=None,force=False,now=None):
        now=now or datetime.now(UTC)
        if kind not in ('operators','lines','stops'):raise TransitUnavailable('Unknown transit directory.')
        params={}
        if kind!='operators':params['operator_id']=identifier(operator_id)
        if kind=='stops' and line_id is not None:params['line_id']=identifier(line_id)
        key=sha256(json.dumps([kind,params],sort_keys=True).encode()).hexdigest()
        try:cached=self.storage.get_cache('transit_directory',key)
        except (ValueError,TypeError):cached=None
        if not force and isinstance(cached,dict):
            checked=instant(cached.get('checked_at'))
            if checked and timedelta(0)<=now-checked<=timedelta(days=7):
                # Re-parse the bounded raw directory, never trust arbitrary cached IDs.
                return parse_metadata(kind,cached.get('payload'))
        payload=self.transport.request(kind,**params)
        rows=parse_metadata(kind,payload)
        # Store normalized public metadata in its documented compact shape. Drop
        # geometry, URLs and irrelevant provider fields to keep Pi storage bounded.
        if kind=='stops':
            compact={'Contents':{'dataObjects':{'ScheduledStopPoint':[{'id':r['id'],'Name':r['name'],
                'Extensions':{'PlatformCode':r['platform'],'ParentStation':r['parent_id'],'LocationType':'1' if r['station'] else '0'}} for r in rows]}}}
        else:
            compact={'content':[{'Id':r['id'],'Name':r['name'],'Monitored':r['monitored'],
                **({'SiriOperatorRef':r['realtime_id']} if kind=='operators' else {'SiriLineRef':r['realtime_id'],'OperatorRef':r['operator_id']})} for r in rows]}
        with self.storage.transaction() as connection:
            connection.execute("INSERT INTO cache(namespace,key,payload,updated_at) VALUES('transit_directory',?,?,?) ON CONFLICT(namespace,key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
                (key,json.dumps({'checked_at':now.isoformat(),'payload':compact}),now.isoformat()))
            # At most twelve directories (including routes/stops), no growing feed archive.
            connection.execute("DELETE FROM cache WHERE namespace='transit_directory' AND key NOT IN (SELECT key FROM cache WHERE namespace='transit_directory' ORDER BY updated_at DESC,key DESC LIMIT 12)")
        return rows

    def verify(self,*,operator_id,stop_id,route_id=None):
        def choose(rows,key):
            found=next((row for row in rows if row['id']==key),None)
            if found is None:raise TransitUnavailable('That selection is no longer in the transit directory. Reload it.')
            return found
        operator=choose(self.get('operators'),operator_id)
        route=choose(self.get('lines',operator_id=operator_id),route_id) if route_id else None
        stop=choose(self.get('stops',operator_id=operator_id,line_id=route_id),stop_id)
        if stop['station']:raise TransitUnavailable('Choose a boarding stop or platform rather than the parent station.')
        return {'operator_id':operator['id'],'operator_name':operator['name'][:100],'agency':operator['realtime_id'],
                'stop_id':stop['id'],'stop_name':stop['name'][:100],'route_id':route['id'] if route else None,
                'line':route['realtime_id'] if route else None,'monitored':operator['monitored'] and (route is None or route['monitored'])}


def delivery_ok(payload,endpoint):
    siri=payload.get('Siri') if isinstance(payload,dict) else None
    service=siri.get('ServiceDelivery') if isinstance(siri,dict) else None
    if not isinstance(service,dict) or service.get('Status') in (False,'false'):return False
    key='StopMonitoringDelivery' if endpoint=='StopMonitoring' else 'StopTimetableDelivery'
    visits='MonitoredStopVisit' if endpoint=='StopMonitoring' else 'TimetabledStopVisit'
    return any(row.get('Status') not in (False,'false') and isinstance(row.get(visits),(list,dict)) for row in items(service.get(key)))


class TransitRuntime:
    INTERVAL=75  # <=48 routine calls/hour, leaving some of the55 budget for setup.

    def __init__(self,service,*,transport=None,clock=monotonic,utcnow=None):
        self.service=service;self.store=service.transit;self.clock=clock;self.utcnow=utcnow or (lambda:datetime.now(UTC))
        self.transport=transport or TransitTransport(TransitBudget(service.storage),self.store.token)
        self.directory=TransitDirectory(service.storage,self.transport)
        self.lock=asyncio.Lock();self.next_request=0;self.turn=0;self.cursor=0
        self.visible=None;self.visible_until=0;self.schedules=set();self.backoff={};self.failures={}

    async def _thread(self,action):
        task=asyncio.create_task(asyncio.to_thread(action))
        try:return await asyncio.shield(task)
        except asyncio.CancelledError:
            # HTTP has a bounded timeout. Do not close its client while a worker uses it.
            try:await task
            except Exception:pass
            raise

    async def discover(self,kind,**params):
        generation=self.store.generation
        async with self.lock:
            result=await self._thread(lambda:self.directory.get(kind,**params))
        if generation!=self.store.generation:raise TransitUnavailable('Transit credentials changed. Try again.')
        return result

    async def verified_selection(self,**params):
        generation=self.store.generation
        async with self.lock:result=await self._thread(lambda:self.directory.verify(**params))
        if generation!=self.store.generation:raise TransitUnavailable('Transit credentials changed. Try again.')
        return result

    async def preview(self,*,operator_id,stop_id,route_id=None):
        selection=await self.verified_selection(operator_id=operator_id,stop_id=stop_id,route_id=route_id)
        if self.lock.locked() or self.clock()<self.next_request:raise TransitQuota('Wait before checking another departure preview.')
        endpoint='StopMonitoring' if selection['monitored'] else 'stoptimetable'
        params={'agency':selection['agency'],'stopcode':selection['stop_id']} if selection['monitored'] else {'operatorref':selection['operator_id'],'monitoringref':selection['stop_id']}
        generation=self.store.generation
        async with self.lock:
            self.next_request=self.clock()+self.INTERVAL
            payload=await self._thread(lambda:self.transport.request(endpoint,**params))
        if generation!=self.store.generation:raise TransitUnavailable('Transit credentials changed. Try again.')
        if not delivery_ok(payload,endpoint):raise TransitUnavailable('Transit feed is unavailable.')
        rows=parse_departures(payload,stop=stop_id,route=selection['line'],now=self.utcnow())[:60]
        directions=sorted({row['direction'] for row in rows if row['direction']})
        return {'directions':directions,'departures':rows[:6],
                'monitored':selection['monitored'],'notice':None if rows else 'No departures in this feed window. All directions can still be saved.'}

    def quiet(self):
        display=self.service.display_state
        return bool(display and (display['mode']!='day' or display['awaiting_clock']))

    @staticmethod
    def group(item):return (item['agency'],item['operator_id'],item['stop_id'],item['monitored'])

    def show(self,item_id):
        self.visible=item_id;self.visible_until=self.clock()+45

    async def refresh(self,item_id=None):
        if self.lock.locked() or self.clock()<self.next_request or self.quiet() or not self.store.token():return False
        entries=self.store.items
        if not entries:return False
        groups={self.group(item):[] for item in entries}
        for item in entries:groups[self.group(item)].append(item)
        self.schedules.intersection_update(groups)
        self.backoff={key:value for key,value in self.backoff.items() if key in groups}
        self.failures={key:value for key,value in self.failures.items() if key in groups}
        if item_id is not None:
            selected=next((self.group(item) for item in entries if item['id']==item_id),None)
            if selected is None:raise TransitUnavailable('Transit favorite not found.')
            if self.clock()<self.backoff.get(selected,0):return False
        else:
            available=[key for key in groups if self.clock()>=self.backoff.get(key,0)]
            if not available:return False
            preferred=next((key for key in available if any(item['id']==self.visible for item in groups[key]) and self.clock()<self.visible_until),None)
            if preferred is None:preferred=next((key for key in available if any(any(name in item['operator_name'].lower() for name in ('stanford','marguerite','caltrain')) for item in groups[key])),None)
            selected=preferred if preferred and self.turn%2==0 else available[self.cursor%len(available)]
            if not preferred or self.turn%2:self.cursor+=1
            self.turn+=1
        agency,operator_id,stop,monitored=selected
        endpoint='stoptimetable' if not monitored or selected in self.schedules else 'StopMonitoring'
        params={'operatorref':operator_id,'monitoringref':stop} if endpoint=='stoptimetable' else {'agency':agency,'stopcode':stop}
        generation=self.store.generation;targets=groups[selected];changed=False
        async with self.lock:
            self.next_request=self.clock()+self.INTERVAL
            try:
                payload=await self._thread(lambda:self.transport.request(endpoint,**params))
                if generation!=self.store.generation:return False
                if not delivery_ok(payload,endpoint):raise TransitUnavailable('Transit feed is unavailable.')
                now=self.utcnow();parsed=[]
                for target in targets:
                    rows=parse_departures(payload,stop=stop,route=target['line'],direction=target['direction'],now=now)
                    parsed.extend(rows)
                    changed=self.store.update(target['id'],target['revision'],generation,departures=rows,now=now) or changed
                if endpoint=='StopMonitoring' and not parsed:self.schedules.add(selected)
                else:self.schedules.discard(selected)
                self.failures.pop(selected,None);self.backoff.pop(selected,None)
            except (TransitUnavailable,OSError,ValueError) as exc:
                if generation!=self.store.generation:return False
                count=min(5,self.failures.get(selected,0)+1);self.failures[selected]=count
                self.backoff[selected]=self.clock()+min(900,self.INTERVAL*2**(count-1))
                if isinstance(exc,TransitQuota):self.next_request=self.clock()+3600
                if endpoint=='StopMonitoring':self.schedules.add(selected)
                for target in targets:
                    changed=self.store.update(target['id'],target['revision'],generation,failed=True,now=self.utcnow()) or changed
        if changed:self.service.publish('transit.updated')
        return True

    async def run(self):
        while True:
            try:await self.refresh()
            except Exception:pass  # No provider payloads, tokens or private stops in logs.
            await asyncio.sleep(15)

    def close(self):self.transport.close()
