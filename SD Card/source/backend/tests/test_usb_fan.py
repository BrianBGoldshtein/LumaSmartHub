"""No USB hardware is accessed. Exercise policy with a fake power switch."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

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


def test_hysteresis_minimum_on_and_discovery_window(rig):
    c,p,s=rig; q=qualify(rig)
    s.now=64; request(c,mode='automatic',qualified=q); assert p.on
    s.now=65; request(c,mode='automatic',qualified=q); assert not p.on
    s.now=124; request(c,mode='automatic',qualified=q); assert not p.on
    s.now=125; request(c,mode='automatic',qualified=q); assert p.on
    s.now=184; request(c,mode='automatic',qualified=q); assert p.on
    s.now=185; request(c,mode='automatic',qualified=q); assert not p.on


@pytest.mark.parametrize('condition', ['heartbeat','storage','updating','heat','bad_sensor','changed_topology'])
def test_unsafe_conditions_restore_power(rig,condition):
    c,p,s=rig; q=cool_off(rig)
    if condition=='heartbeat': s.now+=26; c.tick()
    else:
        if condition in {'storage','updating'}: setattr(s,condition,True)
        elif condition=='heat': s.temperature=60
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
