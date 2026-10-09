"""Local countdown configuration and bounded read-only Google integration."""
import asyncio
from datetime import UTC, date, datetime, time
from time import monotonic
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from .admin_authority import AdminDenied, require_request_admin


class ManualDate(BaseModel):
    model_config={'extra':'forbid'}
    title:str=Field(min_length=1,max_length=100)
    day:str=Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    at:str|None=Field(default=None,pattern=r'^\d{2}:\d{2}$')
    timezone:str=Field(min_length=1,max_length=100)
    annual:bool=Field(default=False,strict=True)
    public:bool=Field(default=False,strict=True)
    item_id:str|None=Field(default=None,pattern=r'^[a-f0-9-]{36}$')
    revision:str|None=Field(default=None,pattern=r'^[a-f0-9-]{36}$')


class PinRequest(BaseModel):
    model_config={'extra':'forbid'}
    calendar_id:str=Field(min_length=1,max_length=1024)
    event_id:str=Field(pattern=r'^[A-Za-z0-9_]{1,1024}$')
    public:bool=Field(default=False,strict=True)


class DateSearch(BaseModel):
    model_config={'extra':'forbid'}
    calendar_id:str=Field(min_length=1,max_length=1024)
    start:str=Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    end:str=Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    page_token:str|None=Field(default=None,max_length=2048)


class Revision(BaseModel):
    model_config={'extra':'forbid'}
    revision:str=Field(pattern=r'^[a-f0-9-]{36}$')


class Visibility(Revision):
    public:bool=Field(strict=True)


class CountdownRuntime:
    def __init__(self,service,google,google_lock,clock=monotonic):
        self.service,self.google,self.google_lock,self.clock=service,google,google_lock,clock
        self.refresh_lock=asyncio.Lock()
        self.next_refresh=0
        self.next_search=0

    async def refresh(self):
        if self.refresh_lock.locked() or self.clock()<self.next_refresh: return False
        async with self.refresh_lock:
            self.next_refresh=self.clock()+60
            pins=[dict(item) for item in self.service.countdowns.items if item['source']=='google']
            changed=False
            for item in pins:
                event=None;state='unlinked'
                if self.google.authorized():
                    try:
                        async with self.google_lock:
                            result=await asyncio.to_thread(self.google.countdown_event,calendar_id=item['calendar_id'],event_id=item['event_id'],timezone=item['timezone'])
                        event,state=result['event'],result['state']
                    except Exception:
                        state='stale'
                elif item.get('state')=='unlinked':
                    continue
                changed=self.service.countdowns.refresh(item['id'],item['revision'],event=event,
                    state=None if state=='ready' else state,now=datetime.now(UTC)) or changed
            if changed: self.service.publish('countdowns.updated')
        return True

    async def run(self):
        while True:
            try: await self.refresh()
            except Exception: pass  # No provider errors or private titles in logs.
            await asyncio.sleep(300)


def install_countdown_api(app,service,google,google_lock,local_only):
    runtime=CountdownRuntime(service,google,google_lock)
    app.state.countdown_runtime=runtime

    def owner_access():
        require_request_admin()
        # First-run setup can save dates before optional phone/PIN enrollment.
        if service.settings.onboarding_completed and service.snapshot()['privacy_redacted']:
            raise HTTPException(403,'Unlock private information to configure countdowns.')

    def configuration():
        return JSONResponse(service.countdowns.configuration(datetime.now(UTC)),headers={'Cache-Control':'no-store'})

    def changed(action):
        try: action()
        except ValueError as exc: raise HTTPException(409,str(exc)) from None
        service.publish('countdowns.updated')
        return configuration()

    @app.get('/api/v1/countdowns',dependencies=[Depends(local_only)])
    async def settings():
        owner_access();return configuration()

    @app.post('/api/v1/countdowns/manual',dependencies=[Depends(local_only)])
    async def save_manual(payload:ManualDate):
        owner_access()
        return changed(lambda:service.countdowns.save_manual(**payload.model_dump()))

    @app.patch('/api/v1/countdowns/{item_id}/visibility',dependencies=[Depends(local_only)])
    async def visibility(item_id:str,payload:Visibility):
        owner_access()
        return changed(lambda:service.countdowns.set_public(item_id,payload.revision,payload.public))

    @app.delete('/api/v1/countdowns/{item_id}',dependencies=[Depends(local_only)])
    async def remove(item_id:str,payload:Revision):
        owner_access()
        return changed(lambda:service.countdowns.remove(item_id,payload.revision))

    @app.post('/api/v1/countdowns/search',dependencies=[Depends(local_only)])
    async def search(payload:DateSearch):
        owner_access()
        if not google.authorized(): raise HTTPException(409,'Connect Google Calendar first.')
        try:
            start,end=date.fromisoformat(payload.start),date.fromisoformat(payload.end)
            zone=ZoneInfo(service.settings.timezone)
            if not 1<=(end-start).days<=93 or start<datetime.now(zone).date() or end.year>2100: raise ValueError()
        except ValueError: raise HTTPException(422,'Choose a future date window of 1 to 93 days, ending by 2100.') from None
        if runtime.clock()<runtime.next_search: raise HTTPException(429,'Wait five seconds before searching again.')
        runtime.next_search=runtime.clock()+5
        try:
            async with google_lock:
                owner_access()
                result=await asyncio.to_thread(google.countdown_candidates,calendar_id=payload.calendar_id,
                    start=datetime.combine(start,time.min,zone),end=datetime.combine(end,time.min,zone),
                    timezone=service.settings.timezone,page_token=payload.page_token)
        except AdminDenied: raise
        except Exception: raise HTTPException(502,'Could not load this date window. Saved countdowns are unchanged.') from None
        owner_access()  # Do not return private search results after a presence lease expires.
        events=[{'id':e.id,'calendar_id':e.calendar_id,'title':e.summary[:100],'start':e.start.isoformat(),
                 'end':e.end.isoformat(),'all_day':e.all_day,'color':e.event_color or e.calendar_color} for e in result['events']]
        return JSONResponse({'events':events,'next_page':result['next_page']},headers={'Cache-Control':'no-store'})

    @app.post('/api/v1/countdowns/google',dependencies=[Depends(local_only)])
    async def pin(payload:PinRequest):
        owner_access()
        if not google.authorized(): raise HTTPException(409,'Connect Google Calendar first.')
        if len(service.countdowns.items)>=12: raise HTTPException(409,'Keep at most 12 countdowns.')
        try:
            async with google_lock:
                owner_access()
                result=await asyncio.to_thread(google.countdown_event,calendar_id=payload.calendar_id,
                    event_id=payload.event_id,timezone=service.settings.timezone)
        except AdminDenied: raise
        except Exception: raise HTTPException(502,'Could not verify this event. Nothing was pinned.') from None
        owner_access()
        if result['state']!='ready' or result['event'] is None: raise HTTPException(409,'This event is no longer available.')
        return changed(lambda:service.countdowns.pin_google(result['event'],timezone=service.settings.timezone,now=datetime.now(UTC),public=payload.public))

    @app.post('/api/v1/countdowns/refresh',dependencies=[Depends(local_only)])
    async def refresh():
        owner_access()
        if not await runtime.refresh(): raise HTTPException(429,'Refresh is running or was attempted within the last minute.')
        owner_access();return configuration()

    return runtime
