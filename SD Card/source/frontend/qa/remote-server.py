"""Disposable TLS/browser qualification only: fake phone/account, real proofs.

Never installed on a Pi. No real provider, radio, update or protected broker.
Start on isolated Linux with an explicit temporary data/frontend directory.
"""
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from fastapi.responses import JSONResponse
from luma.api import create_app
from luma.models import CalendarEvent, WeatherSnapshot
from luma.shortcut_gateway import create_gateway
from luma import update_api

ORIGIN='https://luma.example-tail.ts.net'
PHONE='AA:BB:CC:DD:EE:FF'
core=create_app(data_dir=os.environ['REMOTE_QA_DATA'])
service=core.state.luma;service.display_clock_trusted=lambda:True
core.state.security.set_pin('123456')
service.update_settings({'phone_address':PHONE,'visible_calendar_ids':['classes'],
                         'todo_calendar_id':'tasks','todo_completed_color_id':'8'})
linked=True
def connect():
    core.state.bluetooth.remote_authorized.begin(PHONE,'/fake-phone','/fake-phone/source')
    core.state.bluetooth.remote_authorized.heartbeat(PHONE);service.phone_seen()
connect()
now=datetime.now(UTC)
service.replace_events([CalendarEvent('lecture','classes','A very long lecture title with room and overlapping appointments',now+timedelta(minutes=20),now+timedelta(hours=2),calendar_color='#a78bce',location='Building 550'),
    CalendarEvent('task','tasks','Finish the assignment and review tomorrow’s notes',now.replace(hour=0,minute=0,second=0),now.replace(hour=0,minute=0,second=0)+timedelta(days=2),all_day=True,etag='"fake-etag"',calendar_writable=True)])
service.todo_write_authorized=True
service.calendar_synced_at=now
core.state.profile_calendars.account('primary').status['last_synced']=now.isoformat()
core.state.google.authorized=lambda:True
core.state.google.configured=lambda:True
core.state.google.task_write_authorized=lambda:True
core.state.google.list_calendars=lambda:[{'id':'classes','summary':'Classes','background_color':'#a78bce'}, {'id':'tasks','summary':'Tasks','background_color':'#91efd0'}]
core.state.google.event_colors=lambda:[{'id':'8','background':'#e1e1e1'}]
actions=[]
def recolor(**values):
    task=next(event for event in service.events if event.id==values['event_id'])
    assert values['expected_etag']==task.etag
    actions.append('task')
    return replace(task,event_color_id=values['color_id'],event_color='#e1e1e1',etag='"changed-etag"')
core.state.google.recolor_task=recolor
guest=core.state.profiles.create_secondary('Alex')
core.state.profiles.bind_phone(guest.id,'AA:BB:CC:DD:EE:02')
guest=core.state.profiles.get(guest.id)
core.state.profiles.set_setup(guest.id,'ready',wall_share_approved=True)
core.state.profiles.update_personal(guest.id,{'visible_calendar_ids':['classes'],'todo_calendar_id':'tasks','todo_completed_color_id':'8'})
guest_account=core.state.profile_calendars.account(guest.id)
guest_account.events=[CalendarEvent('lecture','classes','Alex PRIVATE seminar',now+timedelta(minutes=30),now+timedelta(hours=2)),
    CalendarEvent('task','tasks','Alex PRIVATE assignment',now.replace(hour=0,minute=0,second=0),now.replace(hour=0,minute=0,second=0)+timedelta(days=2),all_day=True,etag='"guest-etag"',calendar_writable=True)]
guest_account.status['last_synced']=now.isoformat()
guest_account.google.authorized=lambda:True
guest_account.google.configured=lambda:True
guest_account.google.task_write_authorized=lambda:True
guest_account.google.list_calendars=core.state.google.list_calendars
guest_account.google.event_colors=core.state.google.event_colors
def guest_recolor(**values):
    task=next(event for event in guest_account.events if event.id==values['event_id'])
    assert values['expected_etag']==task.etag
    return replace(task,event_color_id=values['color_id'],event_color='#e1e1e1',etag='"guest-updated"')
guest_account.google.recolor_task=guest_recolor
guest_selected=False
# Exercise review/confirmation/progress UI without a signed install, network
# download or root broker. A real archive/switch is a separate release gate.
update_state={'state':'idle','phase':'idle','target_version':None,'message':''}
installed_version='0.2.11'
update_api.package_version=lambda _:installed_version
update_api.latest_release=lambda current:{'state':'available','current_version':current,
    'version':'0.3.0','release_notes':'Synthetic signed-candidate review. No Pi install.',
    'published_at':'2026-10-08T12:00:00Z','release_url':'https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.3.0','bundle':b'QA-only-never-installed'}
async def update_request(payload):
    if payload['action']=='status':return dict(update_state)
    assert payload['action']=='install'
    actions.append('update')
    update_state.update(state='installing',phase='switching',target_version='0.3.0',message='Synthetic services restarting',elapsed_seconds=1)
    return {'accepted':True,'version':'0.3.0'}
update_api.update_request=update_request
app=create_gateway(transport=httpx.ASGITransport(app=core,client=('127.0.0.1',1234)),frontend_dir=os.environ['REMOTE_QA_FRONTEND'])

@app.middleware('http')
async def qa_only(request,call_next):
    global linked
    if linked:
        core.state.bluetooth.remote_authorized.heartbeat(PHONE);service.phone_seen()
    if request.url.path=='/qa/ticket':
        ticket=core.state.companion.issue_ticket('123456',ORIGIN)
        return JSONResponse({'url':ORIGIN+'/remote/#enroll='+ticket})
    if request.url.path=='/qa/guest-ticket':
        global guest_selected
        guest_selected=True
        phone=core.state.bluetooth.runtime(guest.id)
        phone.remote_authorized.begin(guest.phone_address,'/guest-phone','/guest-phone/source')
        phone.remote_authorized.heartbeat(guest.phone_address)
        phone.service.phone_seen()
        ticket=core.state.companion.issue_ticket('123456',ORIGIN,profile_id=guest.id)
        return JSONResponse({'url':ORIGIN+'/remote/#enroll='+ticket})
    if guest_selected:
        core.state.bluetooth.runtime(guest.id).remote_authorized.heartbeat(guest.phone_address)
        core.state.bluetooth.runtime(guest.id).service.phone_seen()
    if request.url.path=='/qa/approve':
        pending=core.state.companion.pending_status('123456')
        core.state.companion.approve('123456',pending['device_id'],pending['comparison_code'])
        return JSONResponse({'approved':True})
    if request.url.path=='/qa/disconnect':
        linked=False;core.state.bluetooth.remote_authorized.clear()
        return JSONResponse({'linked':False})
    if request.url.path=='/qa/reconnect':
        linked=True;connect();return JSONResponse({'linked':True})
    if request.url.path=='/qa/theme':
        value=await request.json();service.update_settings({'theme':value['theme']})
        return JSONResponse({'theme':value['theme']})
    if request.url.path=='/qa/actions':
        return JSONResponse({'actions':actions,'timer':service.timer.snapshot(private=False)})
    if request.url.path=='/qa/update-complete':
        global installed_version
        installed_version='0.3.0'
        update_state.update(state='installed',phase='complete',message='Synthetic update installed')
        return JSONResponse({'completed':True})
    if request.url.path=='/qa/revoke':
        for device in core.state.companion.devices('123456'):
            core.state.companion.revoke('123456',device['device_id'])
        return JSONResponse({'revoked':True})
    # Emulate the fixed Serve headers from a trusted TLS loopback proxy.
    request.scope['headers']=[(k,v) for k,v in request.scope['headers'] if k not in (b'tailscale-user-login',b'x-forwarded-proto')]+[
        (b'tailscale-user-login',b'guest@example.test' if guest_selected else b'owner@example.test'),(b'x-forwarded-proto',b'https')]
    return await call_next(request)
