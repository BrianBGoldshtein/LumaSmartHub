"""Signed primary controls and saved GPIO preference; no actual hardware."""
import pytest

from test_companion_api import rig,client,envelope
from test_companion_settings import settings,operation,PATH
from test_gpio_fan import wiring
from test_companion_multiuser_api import app_rig,browser


def attach(rig,wiring):
    c,u,g,s=wiring
    async def wire(value):return c.request(value)
    rig[0].state.fan.request=wire
    return c,u,g,s


async def action(rig,name,ack=True):
    return (await settings(rig,operation('device/fan','POST',{
        'action':name,'acknowledged':ack}))).json()['results'][0]


@pytest.mark.asyncio
async def test_signed_gpio_migration_test_confirm_and_standby_independent_cooling(rig,wiring):
    c,u,g,s=attach(rig,wiring)
    assert (await action(rig,'select_gpio',False))['status']==422
    assert c.backend=='usb' and g.calls==[]
    row=await action(rig,'select_gpio');assert row['status']==200
    runtime=rig[0].state.fan
    assert runtime.preferences()=={'mode':'always_on','qualified_topology':None,'backend':'gpio12'}
    assert u.on and g.on and not row['body']['qualified']
    assert (await action(rig,'automatic'))['status']==409
    assert (await action(rig,'probe'))['body']['probe']=='running'
    s.now=5;c.tick();assert u.on and g.on
    assert (await action(rig,'confirm'))['body']['qualified']
    s.now=65
    assert (await action(rig,'automatic'))['status']==200
    assert u.on and not g.on
    from luma.fan_api import FanRuntime
    fresh=FanRuntime(runtime.storage,runtime.request,connected=lambda:False)
    result=await fresh.poll()
    assert result['backend']=='gpio12' and not result['standby_override'] and not g.on and u.on
    assert fresh.preferences()['mode']=='automatic'


@pytest.mark.asyncio
async def test_gpio_fault_disarms_persisted_approval_and_connection_switch_clears_it(rig,wiring):
    c,u,g,s=attach(rig,wiring)
    await action(rig,'select_gpio');await action(rig,'probe');s.now=5;c.tick()
    await action(rig,'confirm');s.now=65;g.fail=True
    assert (await action(rig,'automatic'))['status']==409
    saved=rig[0].state.fan.preferences()
    assert saved=={'mode':'always_on','qualified_topology':None,'backend':'gpio12'}
    assert u.on and g.on
    g.fail=False
    row=await action(rig,'select_usb');assert row['status']==200 and row['body']['backend']=='usb'
    assert rig[0].state.fan.preferences()=={'mode':'always_on','qualified_topology':None}
    assert u.on and g.on


@pytest.mark.asyncio
async def test_lost_primary_cannot_select_gpio_even_with_wiring_ack(rig,wiring):
    c,u,g,s=attach(rig,wiring)
    pending=envelope(rig,'POST',PATH,{'operations':[
        operation('device/fan','POST',{'action':'select_gpio','acknowledged':True})]})
    rig[0].state.bluetooth.remote_authorized.clear()
    async with client(rig[0]) as browser:
        result=await browser.post('/api/v1/companion/dispatch',json=pending)
    assert result.status_code==403 and c.backend=='usb' and not g.calls


@pytest.mark.asyncio
async def test_secondary_cannot_move_or_test_global_fan_wiring(app_rig,wiring):
    app=app_rig[0];c,u,g,s=wiring
    async def wire(value):return c.request(value)
    app.state.fan.request=wire
    result=await settings(browser(app_rig),operation('device/fan','POST',{
        'action':'select_gpio','acknowledged':True}))
    assert result.status_code==403 and c.backend=='usb' and not g.calls


@pytest.mark.asyncio
async def test_disarmed_wiring_intent_is_durable_even_if_broker_call_fails(rig,wiring):
    c,u,g,s=attach(rig,wiring)
    async def failed_wire(value):
        assert rig[0].state.fan.preferences()=={
            'mode':'always_on','qualified_topology':None,'backend':'gpio12'}
        raise OSError('Synthetic broker unavailable')
    rig[0].state.fan.request=failed_wire
    assert (await action(rig,'select_gpio'))['status']==503
    assert rig[0].state.fan.preferences()['backend']=='gpio12'
    assert not g.calls
