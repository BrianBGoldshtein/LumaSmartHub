"""No USB hardware is accessed. Exercise policy with a fake power switch."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import asyncio
from contextlib import suppress

from luma.usb_fan import FanError, USBFanController, validate_fan_request, usb_storage_attached, update_in_progress


class Power:
    fingerprint = 'a' * 64
    def __init__(self):
        self.on, self.calls, self.fail = True, [], False
    def power_state(self):
        return self.on
    def set_power(self, on):
        self.calls.append(on)
        if self.fail and not on:
            raise OSError('synthetic switch failure')
        self.on = on


@pytest.fixture
def rig():
    power = Power()
    state = SimpleNamespace(now=0., temperature=45., storage=False, updating=False)
    controller = USBFanController(lambda: power, lambda: {'celsius': state.temperature},
        lambda: state.storage, lambda: state.updating, lambda: state.now)
    return controller, power, state


def request(controller, operation='poll', mode='always_on', qualified=None, acknowledged=False):
    return controller.request({'action':'fan', 'operation':operation, 'mode':mode,
        'qualified_topology':qualified, 'acknowledged':acknowledged})


def qualify(rig):
    controller, power, state = rig
    request(controller, 'probe', acknowledged=True)
    assert not power.on
    state.now += 5
    controller.tick()
    assert power.on
    result = request(controller, 'confirm', acknowledged=True)
    assert result['qualified']
    return result['qualified_topology']


def cool_off(rig):
    controller, power, state = rig
    qualified = qualify(rig)
    state.now += 60
    request(controller, mode='automatic', qualified=qualified)
    assert not power.on
    return qualified


@pytest.mark.asyncio
async def test_standby_restores_off_usb_preserves_mode_and_resumes_70_60_control(rig,tmp_path):
    from luma.fan_api import FanRuntime,PREFERENCES
    from luma.storage import Storage
    c,p,s=rig;q=cool_off(rig)
    connected=[False]
    storage=Storage(tmp_path/'luma.db')
    saved={'mode':'automatic','qualified_topology':q}
    storage.set_cache('device',PREFERENCES,saved)
    async def wire(packet): return c.request(packet)
    runtime=FanRuntime(storage,wire,connected=lambda:connected[0])
    result=await runtime.poll()
    assert p.on and result['standby_override'] and result['mode']=='automatic'
    assert 'Standby' in result['reason'] and runtime.preferences()==saved
    calls=list(p.calls)
    for minute in range(1,61):
        s.now+=60
        result=await runtime.poll()
        assert p.on and result['mode']=='automatic'
    assert p.calls==calls  # No repeated restoration writes or discovery cycling.
    connected[0]=True
    result=await runtime.poll()
    assert not result['standby_override'] and not p.on and runtime.preferences()==saved
    s.temperature=70
    await runtime.poll();assert p.on


@pytest.mark.asyncio
async def test_unknown_phone_presence_fails_on_and_disconnect_race_wins(rig,tmp_path):
    from luma.fan_api import FanRuntime,PREFERENCES
    from luma.storage import Storage
    c,p,s=rig;q=cool_off(rig)
    storage=Storage(tmp_path/'luma.db')
    storage.set_cache('device',PREFERENCES,{'mode':'automatic','qualified_topology':q})
    connected=[True]
    packets=[]
    async def wire(packet):
        packets.append(packet)
        if len(packets)==1: connected[0]=False
        return c.request(packet)
    runtime=FanRuntime(storage,wire,connected=lambda:connected[0])
    assert (await runtime.poll())['standby_override'] and p.on
    assert packets[-1]['operation']=='keep_on' and packets[-1]['mode']=='always_on'
    runtime.connected=lambda:(_ for _ in ()).throw(RuntimeError('observer unavailable'))
    assert (await runtime.poll())['standby_override'] and p.on


@pytest.mark.asyncio
async def test_phone_loss_cancels_in_progress_physical_probe_immediately(rig,tmp_path):
    from luma.fan_api import FanRuntime
    from luma.storage import Storage
    c,p,s=rig
    connected=[True]
    async def wire(packet): return c.request(packet)
    runtime=FanRuntime(Storage(tmp_path/'luma.db'),wire,connected=lambda:connected[0])
    await runtime.poll()
    request(c,'probe',acknowledged=True);assert not p.on
    connected[0]=False
    result=await runtime.poll()
    assert p.on and result['probe']=='idle' and result['standby_override']


@pytest.mark.asyncio
async def test_last_phone_loss_wakes_fan_worker_without_waiting_for_heartbeat(rig,tmp_path):
    from luma.fan_api import PREFERENCES
    from luma.api import create_app
    c,p,s=rig;q=cool_off(rig)
    app=create_app(data_dir=tmp_path)
    runtime=app.state.fan
    runtime.storage.set_cache('device',PREFERENCES,{'mode':'automatic','qualified_topology':q})
    children=[]
    for i in range(2):
        guest=app.state.profiles.create_secondary(f'Guest {i}')
        phone=f'AA:BB:CC:DD:EE:{i+1:02X}'
        app.state.profiles.bind_phone(guest.id,phone)
        child=app.state.bluetooth.runtime(guest.id)
        child.remote_authorized.begin_bonded(phone,'/phone',dict(Address=phone,Paired=True,
            Bonded=True,Trusted=True,Connected=True,ServicesResolved=True,Blocked=False))
        child.remote_authorized.heartbeat(phone);child.service.phone_seen();children.append(child)
    polled=asyncio.Event()
    async def wire(packet):
        result=c.request(packet);polled.set();return result
    runtime.request=wire
    task=asyncio.create_task(runtime.run())
    try:
        await asyncio.wait_for(polled.wait(),1)
        assert not p.on
        polled.clear();children[0].remote_authorized.clear()
        await asyncio.wait_for(polled.wait(),1)
        assert not p.on  # Another registered phone is still present.
        polled.clear();children[1].remote_authorized.clear()
        await asyncio.wait_for(polled.wait(),1)
        assert p.on
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError): await task


@pytest.mark.asyncio
async def test_standby_probe_rejected_and_secondary_without_calendars_counts_as_present(tmp_path):
    from luma.api import create_app
    app=create_app(data_dir=tmp_path)
    app.state.security.set_pin('123456')
    request=app.state.fan.request=AsyncMock(return_value={'available':True,'qualified':True,
        'qualified_topology':'a'*64,'mode':'always_on','usb_power':'on','probe':'idle','reason':'test'})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=('127.0.0.1',1)),base_url='http://127.0.0.1:8742') as client:
        await client.post('/api/v1/admin/unlock',json={'pin':'123456'})
        assert (await client.post('/api/v1/device/fan',json={'action':'probe','acknowledged':True})).status_code==409
        assert not request.called
        app.state.luma.state.phone_connected=True  # A raw/stale link flag is not remote authority.
        assert (await client.get('/api/v1/device/fan')).json()['standby_override']
        app.state.luma.state.phone_connected=False
        guest=app.state.profiles.create_secondary('Alex')
        phone='AA:BB:CC:DD:EE:02'
        app.state.profiles.bind_phone(guest.id,phone)
        child=app.state.bluetooth.runtime(guest.id)
        child.remote_authorized.begin_bonded(phone,'/phone',dict(Address=phone,Paired=True,
            Bonded=True,Trusted=True,Connected=True,ServicesResolved=True,Blocked=False))
        child.remote_authorized.heartbeat(phone);child.service.phone_seen()
        assert not (await client.get('/api/v1/device/fan')).json()['standby_override']
        child.remote_authorized.clear()
        assert (await client.get('/api/v1/device/fan')).json()['standby_override']


@pytest.mark.parametrize('field,value', [('operation', []), ('mode', {}), ('qualified_topology', '../dev'),
    ('acknowledged', 1), ('operation', 'shell'), ('mode', 'pwm')])
def test_wire_rejects_invalid_values(field, value):
    data = {'action':'fan','operation':'poll','mode':'always_on','qualified_topology':None,'acknowledged':False}
    data[field] = value
    with pytest.raises(FanError): validate_fan_request(data)


def test_unknown_wire_fields_and_unacknowledged_test_rejected():
    with pytest.raises(FanError): validate_fan_request({'action':'fan','path':'/dev/usb'})
    with pytest.raises(FanError): request(USBFanController(), 'probe')


def test_default_and_unqualified_automatic_never_cut_power(rig):
    c, p, s = rig
    request(c); s.now=100
    request(c, mode='automatic')
    assert p.on and False not in p.calls


def test_external_power_change_is_restored_and_disables_automatic(rig):
    c,p,s=rig
    request(c)
    p.on=False
    c.tick()
    assert p.on and c.fault and c.mode=='always_on'


def test_probe_restores_without_api_and_requires_confirmation(rig):
    c, p, s = rig
    request(c, 'probe', acknowledged=True)
    assert not p.on and not c.status()['qualified']
    with pytest.raises(FanError): request(c, 'confirm', acknowledged=True)
    s.now=5; c.tick()
    assert p.on and c.status()['probe']=='confirm'
    assert request(c, 'confirm', acknowledged=True)['qualified']


def test_always_on_cancels_probe_immediately(rig):
    c,p,s=rig
    request(c,'probe',acknowledged=True)
    request(c,'keep_on')
    assert p.on and c.status()['probe']=='idle'


@pytest.mark.parametrize('field', ['storage', 'updating'])
def test_storage_even_unmounted_and_update_prevent_probe_and_off(rig, field):
    c,p,s=rig; setattr(s,field,True)
    with pytest.raises(FanError): request(c,'probe',acknowledged=True)
    assert p.on and False not in p.calls


def test_minimum_on_then_stays_off_without_discovery_windows(rig):
    c,p,s=rig; q=qualify(rig)
    s.now=64; request(c,mode='automatic',qualified=q); assert p.on
    s.now=65; request(c,mode='automatic',qualified=q); assert not p.on
    calls=list(p.calls)
    for now in range(70, 14471, 5):
        s.now=now
        s.temperature=(55,60,65,69.9)[now//5%4]
        result=request(c,mode='automatic',qualified=q)
        c.tick()
        assert not p.on and result['mode']=='automatic'
    assert p.calls==calls
    assert result['max_off_seconds'] is None and result['discovery_windows'] is False


def test_exact_70_on_60_off_hysteresis_and_no_threshold_chatter(rig):
    c,p,s=rig; q=cool_off(rig)
    for reading in (60,65,69.9):
        s.temperature=reading
        request(c,mode='automatic',qualified=q)
        assert not p.on
    s.temperature=70
    request(c,mode='automatic',qualified=q)
    assert p.on
    for reading in (69,65,60.1):
        s.now+=20; s.temperature=reading
        request(c,mode='automatic',qualified=q)
        assert p.on
    s.temperature=60
    request(c,mode='automatic',qualified=q)
    assert not p.on
    calls=list(p.calls)
    for reading in (60.1,59.9,65,69.99):
        s.now+=10; s.temperature=reading
        request(c,mode='automatic',qualified=q)
        assert not p.on
    assert p.calls==calls


def test_manual_keep_on_recovers_usb_after_extended_quiet_period(rig):
    c,p,s=rig; q=cool_off(rig)
    for now in range(70,3671,5):
        s.now=now
        request(c,mode='automatic',qualified=q)
    assert not p.on
    result=request(c,'keep_on',mode='always_on',qualified=q)
    assert p.on and result['mode']=='always_on' and result['qualified']
    s.storage=True
    request(c,mode='automatic',qualified=q)
    assert p.on and 'storage' in c.status()['reason']


@pytest.mark.parametrize('condition', ['heartbeat','storage','updating','heat','bad_sensor','changed_topology'])
def test_unsafe_conditions_restore_power(rig,condition):
    c,p,s=rig; q=cool_off(rig)
    if condition=='heartbeat': s.now+=26; c.tick()
    else:
        if condition in {'storage','updating'}: setattr(s,condition,True)
        elif condition=='heat': s.temperature=70
        elif condition=='bad_sensor': s.temperature=float('nan')
        else: q='b'*64
        request(c,mode='automatic',qualified=q)
    assert p.on


def test_media_access_and_shutdown_restore_power(rig):
    c,p,s=rig; cool_off(rig)
    with c.media_access(): assert p.on
    c.close(); assert p.on


def test_switch_failure_disables_automatic_and_attempts_restoration(rig):
    c,p,s=rig; q=qualify(rig); p.fail=True; s.now+=60
    request(c,mode='automatic',qualified=q)
    assert p.on and not c.status()['available'] and not c.status()['qualified']


def test_storage_detection_includes_usb_interface_without_mount(tmp_path):
    usb,blocks=tmp_path/'usb',tmp_path/'blocks'
    usb.mkdir();blocks.mkdir()
    assert not usb_storage_attached(usb,blocks)
    interface=usb/'1-1:1.0';interface.mkdir();(interface/'bInterfaceClass').write_text('08\n')
    assert usb_storage_attached(usb,blocks)
    assert usb_storage_attached(tmp_path/'missing',blocks)


def test_update_guard_reads_durable_state_and_fails_closed(tmp_path):
    assert not update_in_progress(tmp_path)
    status=tmp_path/'.luma-update-status.json'
    status.write_text('{"state":"installing"}')
    assert update_in_progress(tmp_path)
    status.write_text('broken')
    assert update_in_progress(tmp_path)


def test_linux_transfer_uses_bounded_port_power_requests_and_expected_device(monkeypatch):
    import ctypes, fcntl, os, stat, struct
    from pathlib import Path
    from luma.usb_fan import Hub, LinuxUSBPower
    power=LinuxUSBPower.__new__(LinuxUSBPower);power.dev_usb=Path('/dev/bus/usb')
    opened=[];requests=[]
    monkeypatch.setattr(os,'open',lambda path,flags: opened.append((path,flags)) or 42)
    monkeypatch.setattr(os,'fstat',lambda fd: SimpleNamespace(st_mode=stat.S_IFCHR,st_rdev=os.makedev(189,1)))
    monkeypatch.setattr(os,'close',lambda fd: None)
    def ioctl(fd,code,body):
        values=struct.unpack('@BBHHHIP',body);requests.append(values)
        assert code==0xc0005500|(len(body)<<16)
        if values[1]==0:
            ctypes.memmove(values[-1],struct.pack('<HH',0x100,0),4)
        return 4 if values[1]==0 else 0
    monkeypatch.setattr(fcntl,'ioctl',ioctl)
    hub=Hub(1,2,False)
    power._transfer(hub,4,False);power._transfer(hub,4,True)
    assert power._transfer(hub,4) is True
    assert requests[0][:6]==(0x23,1,8,4,0,1000)
    assert requests[1][:6]==(0x23,3,8,4,0,1000)
    assert requests[2][:6]==(0xa3,0,0,4,4,1000)
    assert opened[0][0]==Path('/dev/bus/usb/001/002')
    assert opened[0][1]&os.O_NOFOLLOW
    monkeypatch.setattr(os,'fstat',lambda fd: SimpleNamespace(st_mode=stat.S_IFREG,st_rdev=0))
    with pytest.raises(FanError): power._transfer(hub,4,True)


def test_restore_attempts_every_port_even_if_one_fails():
    from luma.usb_fan import Hub, LinuxUSBPower
    power=LinuxUSBPower.__new__(LinuxUSBPower);power.hubs=(Hub(1,2,False),Hub(2,1,True))
    calls=[]
    def transfer(hub,port,on):
        calls.append((hub,port,on))
        if len(calls)==1: raise OSError('test')
    power._transfer=transfer
    with pytest.raises(FanError): power.set_power(True)
    assert len(calls)==8 and all(row[2] is True for row in calls)


@pytest.mark.asyncio
async def test_fan_api_requires_admin_and_preserves_database_preferences(tmp_path):
    from luma.api import create_app
    app=create_app(data_dir=tmp_path)
    app.state.fan.connected=lambda:True  # This test covers admin policy, not phone verification.
    app.state.security.set_pin('123456')
    app.state.fan.request=AsyncMock(return_value={'available':True,'qualified':True,
        'qualified_topology':'a'*64,'mode':'always_on','usb_power':'on','probe':'idle','reason':'test'})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=('127.0.0.1',1)),base_url='http://127.0.0.1:8742') as client:
        assert (await client.get('/api/v1/device/fan')).status_code==403
        assert (await client.post('/api/v1/device/fan',json={'action':'always_on'})).status_code==403
        assert not app.state.fan.request.called
        assert (await client.post('/api/v1/admin/unlock',json={'pin':'123456'})).status_code==200
        response=await client.post('/api/v1/device/fan',json={'action':'confirm','acknowledged':True})
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        assert app.state.fan.preferences()['qualified_topology']=='a'*64
        assert (await client.post('/api/v1/device/fan',json={'action':'probe'})).status_code==422
        assert (await client.post('/api/v1/device/fan',json={'action':'pwm','path':'/dev/foo'})).status_code==422
