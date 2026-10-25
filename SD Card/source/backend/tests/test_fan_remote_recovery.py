"""Real signed primary settings transport with a simulated protected USB broker."""
from types import SimpleNamespace

import pytest

from luma.usb_fan import USBFanController, FanError
from test_usb_fan import Power
from test_companion_api import rig,client,envelope
from test_companion_settings import settings,operation,PATH


def failed_controller(app):
    p=Power();state=SimpleNamespace(now=0,storage=False,updating=False)
    c=USBFanController(lambda:p,lambda:{'celsius':55},lambda:state.storage,
        lambda:state.updating,lambda:state.now)
    packet=lambda op,ack=False:{'action':'fan','operation':op,'mode':'always_on',
        'qualified_topology':None,'acknowledged':ack}
    c.request(packet('poll'));p.fail=True
    with pytest.raises(FanError):c.request(packet('probe',True))
    p.fail=False
    async def wire(value):return c.request(value)
    app.state.fan.request=wire
    return c,p,state


@pytest.mark.asyncio
async def test_signed_primary_can_recover_fault_observe_confirm_then_enable_automatic(rig):
    c,p,s=failed_controller(rig[0])
    result=(await settings(rig,operation('device/fan'))).json()['results'][0]['body']
    assert not result['available'] and result['usb_power']=='on'
    denied=(await settings(rig,operation('device/fan','POST',{'action':'probe'}))).json()['results'][0]
    assert denied['status']==422 and p.on
    async def command(action):
        row=(await settings(rig,operation('device/fan','POST',{'action':action,'acknowledged':True}))).json()['results'][0]
        assert row['status']==200
        return row['body']
    result=await command('probe');assert result['probe']=='running' and not p.on
    s.now+=5;c.tick();assert p.on and c.status()['probe']=='confirm'
    await command('confirm');assert c.status()['qualified']
    s.now+=60
    result=await command('automatic')
    assert result['mode']=='automatic' and result['qualified'] and not p.on
    assert rig[0].state.fan.preferences()['mode']=='automatic'


@pytest.mark.asyncio
@pytest.mark.parametrize('guard',['storage','updating'])
async def test_signed_recovery_cannot_bypass_drive_or_update_guard(rig,guard):
    c,p,s=failed_controller(rig[0]);setattr(s,guard,True);before=len(p.calls)
    result=await settings(rig,operation('device/fan','POST',{'action':'probe','acknowledged':True}))
    assert result.json()['results'][0]['status']==503
    assert p.on and all(p.calls[before:]) and not c.status()['qualified']


@pytest.mark.asyncio
async def test_lost_primary_cannot_submit_even_an_acknowledged_recovery(rig):
    app=rig[0];c,p,s=failed_controller(app);before=list(p.calls)
    pending=envelope(rig,'POST',PATH,{'operations':[
        operation('device/fan','POST',{'action':'probe','acknowledged':True})]})
    app.state.bluetooth.remote_authorized.clear()
    async with client(app) as browser:
        result=await browser.post('/api/v1/companion/dispatch',json=pending)
    assert result.status_code==403 and p.calls==before


@pytest.mark.asyncio
async def test_observed_fault_disarms_saved_qualification_across_broker_restart(rig):
    app=rig[0];c,p,s=failed_controller(app)
    app.state.fan.storage.set_cache('device','usb_fan_v1',{
        'mode':'automatic','qualified_topology':p.fingerprint})
    result=(await settings(rig,operation('device/fan'))).json()['results'][0]['body']
    assert result['fault'] and not result['qualified'] and p.on
    assert app.state.fan.preferences()=={'mode':'always_on','qualified_topology':None}
    # A fresh protected controller models the service restart during an app
    # update. Temperature/time would permit off if old qualification survived.
    fresh=USBFanController(lambda:p,lambda:{'celsius':55},lambda:False,lambda:False,lambda:s.now)
    async def wire(value):return fresh.request(value)
    app.state.fan.request=wire;s.now+=120;before=len(p.calls)
    result=(await settings(rig,operation('device/fan'))).json()['results'][0]['body']
    assert result['mode']=='always_on' and not result['qualified'] and p.on
    assert all(p.calls[before:])
    rejected=(await settings(rig,operation('device/fan','POST',{'action':'automatic'}))).json()['results'][0]
    assert rejected['status']==409 and p.on
