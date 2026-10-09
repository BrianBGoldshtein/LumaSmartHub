"""Disposable guided setup lab. Synthetic pairing only; no owner device/account."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from datetime import UTC, datetime, timedelta
from dataclasses import replace

from fastapi import Request
from fastapi.responses import JSONResponse
from luma.api import create_app
from luma.companion_google import AUTH_URI, TOKEN_URI
from luma.integrations.google_calendar import CLIENT_CONFIG_KEY
from luma.models import CalendarEvent

app=create_app(data_dir=os.environ['USER_QA_DATA'],frontend_dir=os.environ['USER_QA_FRONTEND'])
app.state.security.set_pin('123456')
app.state.luma.update_settings({'onboarding_completed':True})
app.state.luma.display_clock_trusted=lambda:True
clock=[0.0]
voice_clock=[100.0]
app.state.luma.voice_accounts.clock=lambda:voice_clock[0]
app.state.admin.clock=lambda:clock[0]
app.state.luma.storage.set_secret(CLIENT_CONFIG_KEY,json.dumps({'installed':{
    'client_id':'1234567890-fake.apps.googleusercontent.com','client_secret':'synthetic-client-secret',
    'auth_uri':AUTH_URI,'token_uri':TOKEN_URI}}))

class SyntheticPairing:
    adapter='/org/bluez/hci0'
    path=adapter+'/dev_AA_BB_CC_DD_EE_FF'
    def __init__(self):
        self.props={'Adapter':self.adapter,'Address':'AA:BB:CC:DD:EE:FF','Alias':'Alex’s iPhone',
                    'Paired':False,'Bonded':False,'Trusted':False}
    async def open(self):pass
    async def close(self):pass
    async def start_scan(self):pass
    async def stop_scan(self):pass
    async def cancel_pair(self,path):pass
    async def objects(self):return {self.path:{'org.bluez.Device1':self.props}}
    async def properties(self,path):return dict(self.props)
    async def pair(self,path,confirm):
        if not await confirm(path,42817):raise ValueError('Rejected synthetic code')
        self.props.update(Paired=True,Bonded=True)
    async def trust(self,path):self.props['Trusted']=True

app.state.user_setup.pairing.driver_factory=SyntheticPairing

@asynccontextmanager
async def isolated(_):
    try:yield  # Never start daemon workers or contact Google/BlueZ/Tailscale.
    finally:await app.state.user_setup.pairing.close()
app.router.lifespan_context=isolated

@app.middleware('http')
async def qa_only(request:Request,call_next):
    if request.url.path=='/qa/wall-complete':
        uid=(await request.json())['profile_id']
        timer=app.state.luma.personal_timers.for_user(uid)
        original_clock=timer.clock
        timer.clock=lambda:100.0
        try:
            timer.execute('start_timer',{'seconds':1,'label':'LAB alarm'})
            timer.clock=lambda:102.0
            timer.tick(trusted=True)
        finally:timer.clock=original_clock
        app.state.luma.publish('user.timer.updated')
        return JSONResponse({'completed':True})
    if request.url.path=='/qa/wall-tasks':
        profiles=app.state.profiles
        now=datetime.now(UTC)
        for user in profiles.list():
            profiles.update_personal(user.id,{'todo_calendar_id':'tasks','todo_completed_color_id':'5'})
            account=app.state.profile_calendars.account(user.id)
            account.google.task_write_authorized=lambda:True
            account.events.append(CalendarEvent('same_task','tasks',user.nickname+' PRIVATE TASK',now-timedelta(days=1),now+timedelta(days=2),all_day=True,etag='revision',calendar_writable=True))
            def recolor(*,event_id,color_id,expected_etag,owner=account,**kwargs):
                original=next(row for row in owner.events if row.id==event_id)
                return replace(original,event_color_id=color_id,etag=expected_etag+'next')
            account.google.recolor_task=recolor
        app.state.luma.machine.settings=profiles.storage.load_settings()
        app.state.luma.publish('user.calendar.updated')
        return JSONResponse({'ready':True})
    if request.url.path=='/qa/voice-initialize':
        service,profiles=app.state.luma,app.state.profiles
        profiles.rename('primary','Brian')
        users=[profiles.get('primary')]+[profiles.create_secondary(name) for name in ['Alex','Sam','Casey','Robin']]
        now=datetime.now(UTC)
        service.update_settings({'voice_enabled':True,'timezone':'UTC'})
        for index,user in enumerate(users):
            profiles.bind_phone(user.id,f'AA:BB:CC:DD:EE:{index+1:02X}')
            profiles.set_setup(user.id,'ready',wall_share_approved=True)
            profiles.update_personal(user.id,{'visible_calendar_ids':['events']})
            account=app.state.profile_calendars.account(user.id)
            account.google.authorized=lambda:True
            account.events=[CalendarEvent('same-event','events',user.nickname+' PRIVATE EVENT',now+timedelta(minutes=30),now+timedelta(hours=1))]
            account.status['last_synced']=now.isoformat()
            child=app.state.bluetooth.runtime(user.id)
            child.remote_authorized.clock=lambda:100.0
            child.remote_authorized.begin(profiles.get(user.id).phone_address,'/synthetic/'+user.id,'/synthetic/source/'+user.id)
            child.remote_authorized.heartbeat(profiles.get(user.id).phone_address)
            child.service.phone_seen(now)
        service.machine.settings=profiles.storage.load_settings()
        service.replace_events(app.state.profile_calendars.account('primary').events,now)
        service.calendar_synced_at=now
        return JSONResponse({'users':[{'id':user.id,'nickname':user.nickname} for user in users]})
    if request.url.path=='/qa/voice-expire':
        voice_clock[0]+=31
        app.state.luma.publish('voice.account.updated')
        return JSONResponse({'changed':True})
    if request.url.path=='/qa/voice-disconnect':
        user_id=(await request.json())['profile_id']
        app.state.bluetooth.runtime(user_id).remote_authorized.clear()
        app.state.luma.publish('user.presence.updated')
        return JSONResponse({'changed':True})
    if request.url.path=='/qa/theme':
        app.state.luma.update_settings({'theme':(await request.json())['theme']})
        return JSONResponse({'changed':True})
    if request.url.path=='/qa/expire-primary':
        clock[0]+=301
        return JSONResponse({'expired':True})
    if request.url.path in {'/qa/authorize','/qa/disconnect'}:
        user=app.state.profiles.by_phone('AA:BB:CC:DD:EE:FF')
        child=app.state.bluetooth.runtime(user.id)
        child.remote_authorized.clock=lambda:0.0
        if request.url.path=='/qa/authorize':
            child.remote_authorized.begin(user.phone_address,'/synthetic','/synthetic/source')
            child.remote_authorized.heartbeat(user.phone_address)
            child.service.phone_seen()
        else:child.remote_authorized.clear()
        return JSONResponse({'changed':True})
    if request.url.path=='/qa/google-linked':
        user=app.state.profiles.by_phone('AA:BB:CC:DD:EE:FF')
        account=app.state.profile_calendars.account(user.id)
        account.google.authorized=lambda:True
        account.google.task_write_authorized=lambda:True
        account.google.list_calendars=lambda:[{'id':'alex-events','summary':'Alex classes','background_color':'#7986cb'},
            {'id':'alex-tasks','summary':'Alex tasks','background_color':'#33b679','access_role':'owner'}]
        account.google.event_colors=lambda:[{'id':'2','background':'#7ae7bf'},{'id':'11','background':'#dc2127'}]
        account.google.fetch_events=lambda *args:[]
        return JSONResponse({'changed':True})
    if request.url.path=='/qa/more-users':
        for name in ['Guest two','Guest three','Guest four']:
            app.state.profiles.create_secondary(name)
        return JSONResponse({'created':True})
    return await call_next(request)
