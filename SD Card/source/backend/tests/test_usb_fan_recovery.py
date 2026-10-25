"""Fault/readback simulations only. Never access or switch real USB devices."""
from types import SimpleNamespace

import pytest

from luma import usb_fan
from luma.usb_fan import FanError, Hub, LinuxUSBPower
from test_usb_fan import rig, request, qualify


@pytest.mark.parametrize('desired',[False,True])
def test_usb3_delayed_readback_waits_once_without_repeated_power_writes(monkeypatch,desired):
    now=[0.];writes=[];sleeps=[];old=not desired
    def pause(seconds):sleeps.append(seconds);now[0]+=seconds
    monkeypatch.setattr(usb_fan,'time',SimpleNamespace(sleep=pause))
    power=LinuxUSBPower.__new__(LinuxUSBPower)
    power.hubs=(Hub(1,2,False),Hub(2,1,True))
    def transfer(hub,port,on=None):
        if on is not None:writes.append((hub,port,on));return
        return desired if now[0]>=.1 else old  # Acknowledged write, status not settled yet.
    power._transfer=transfer
    power.set_power(desired)
    assert sleeps==[.15] and len(writes)==8
    assert all(value is desired for _,_,value in writes)


def test_persistent_mixed_readback_is_still_a_fault_after_settle(monkeypatch):
    monkeypatch.setattr(usb_fan,'time',SimpleNamespace(sleep=lambda _:None))
    power=LinuxUSBPower.__new__(LinuxUSBPower)
    power.hubs=(Hub(1,2,False),Hub(2,1,True));writes=[]
    def transfer(hub,port,on=None):
        if on is not None:writes.append(on);return
        return hub.usb3
    power._transfer=transfer
    with pytest.raises(FanError) as error:power.set_power(False)
    assert error.value.code=='power_unconfirmed' and writes==[False]*8


def test_latched_fault_can_retest_but_never_automatically_requalifies(rig):
    c,p,s=rig;q=qualify(rig)
    p.fail=True;s.now+=60
    assert not request(c,mode='automatic',qualified=q)['available']
    p.fail=False
    for _ in range(10):
        s.now+=5
        status=request(c,mode='automatic',qualified=q)
        assert p.on and not status['available'] and not status['qualified']
    calls=list(p.calls)
    with pytest.raises(FanError):request(c,'probe')  # No acknowledgment: no writes.
    assert p.calls==calls
    status=request(c,'probe',acknowledged=True)
    assert not p.on and status['probe']=='running' and not status['qualified']
    assert status['fault_code'] is None
    s.now+=5;c.tick()
    assert p.on and c.status()['probe']=='confirm' and not c.status()['qualified']
    assert request(c,'confirm',acknowledged=True)['qualified']


def test_duplicate_probe_cannot_extend_the_five_second_interruption(rig):
    c,p,s=rig
    request(c,'probe',acknowledged=True);deadline=c.probe_until
    s.now+=2
    with pytest.raises(FanError,match='already running'):request(c,'probe',acknowledged=True)
    assert c.probe_until==deadline and p.calls.count(False)==1
    s.now=deadline;c.tick();assert p.on


def test_keep_on_write_error_is_latched_and_restoration_still_attempted(rig):
    c,p,s=rig;request(c)
    calls=[]
    def failed(on):calls.append(on);raise OSError(5,'synthetic private device path')
    p.set_power=failed
    result=request(c,'keep_on')
    assert result['fault'] and result['fault_code']=='usb_io'
    assert result['usb_power']=='unknown' and not result['qualified']
    assert calls==[True,True]  # Initial restore + independent best-effort restore.
    assert 'private' not in str(result)


@pytest.mark.parametrize('guard',['storage','updating'])
def test_recovery_probe_still_refuses_storage_or_update(rig,guard):
    c,p,s=rig;request(c);p.on=False;c.tick();assert c.fault
    setattr(s,guard,True);before=len(p.calls)
    with pytest.raises(FanError):request(c,'probe',acknowledged=True)
    assert p.on and all(p.calls[before:])
    assert not c.status()['qualified']
