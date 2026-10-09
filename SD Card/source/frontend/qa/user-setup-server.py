"""Disposable guided setup lab. Synthetic pairing only; no owner device/account."""
import asyncio
from contextlib import asynccontextmanager
import json
import os

from fastapi import Request
from fastapi.responses import JSONResponse
from luma.api import create_app
from luma.companion_google import AUTH_URI, TOKEN_URI
from luma.integrations.google_calendar import CLIENT_CONFIG_KEY

app=create_app(data_dir=os.environ['USER_QA_DATA'],frontend_dir=os.environ['USER_QA_FRONTEND'])
app.state.security.set_pin('123456')
app.state.luma.update_settings({'onboarding_completed':True})
app.state.luma.display_clock_trusted=lambda:True
clock=[0.0]
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
