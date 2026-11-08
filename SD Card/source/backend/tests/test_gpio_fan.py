"""Fixed-line ABI and cooling simulations; no real GPIO/USB is accessed."""
from types import SimpleNamespace
import os
import stat
import struct
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from luma import gpio_fan as hw
from luma.usb_fan import USBFanController, FanError
from test_usb_fan import Power


class Board(Power):
    fingerprint = 'b' * 64
    def __init__(self):
        super().__init__()
        self.closed = False
    def close(self):
        self.set_power(True)
        self.closed = True


@pytest.fixture
def wiring():
    s = SimpleNamespace(now=0., temperature=55., network=True, storage=True, updating=False)
    usb, board = Power(), Board()
    hub = USBFanController(lambda:usb, lambda:{'celsius':s.temperature},
        lambda:s.storage, lambda:s.updating, lambda:s.now, network=lambda:s.network)
    gpio = hw.GPIOFanController(lambda:board, temperature=lambda:{'celsius':s.temperature},
        updating=lambda:s.updating, clock=lambda:s.now)
    return hw.FanController(hub,gpio), usb, board, s


def packet(op='poll', *, backend='gpio12', mode='always_on', qualified=None, ack=False):
    return {'action':'fan','operation':op,'backend':backend,'mode':mode,
            'qualified_topology':qualified,'acknowledged':ack}


def qualified(wiring):
    c,u,g,s=wiring
    c.request(packet('keep_on'))
    assert not c.request(packet('probe',ack=True))['qualified']
    assert not g.on and u.on
    s.now+=5;c.tick()
    result=c.request(packet('confirm',ack=True))
    assert g.on and u.on and result['qualified']
    return result['qualified_topology']


def test_no_gpio_claim_without_opt_in_and_networked_usb_is_never_cut(wiring):
    c,u,g,s=wiring
    c.request(packet(backend='usb'));c.tick()
    assert c.gpio.power is None and g.calls==[]
    q=qualified(wiring);s.now+=60
    result=c.request(packet(mode='automatic',qualified=q))
    assert not g.on and result['fan_power']=='off' and result['usb_power']=='on'
    assert result['backend']=='gpio12' and result['gpio_bcm']==12
    assert False not in u.calls


def test_gpio_exact_hysteresis_no_discovery_and_independent_heartbeat(wiring):
    c,u,g,s=wiring;q=qualified(wiring)
    s.now=64;c.request(packet(mode='automatic',qualified=q));assert g.on
    s.now=65;c.request(packet(mode='automatic',qualified=q));assert not g.on
    before=len(g.calls)
    for temperature in (60,61,65,69.9)*30:
        s.now+=5;s.temperature=temperature
        c.request(packet(mode='automatic',qualified=q));c.tick()
        assert not g.on and u.on
    assert len(g.calls)==before
    s.temperature=70;c.request(packet(mode='automatic',qualified=q));assert g.on
    s.temperature=60;s.now+=59;c.request(packet(mode='automatic',qualified=q));assert g.on
    s.now+=1;c.request(packet(mode='automatic',qualified=q));assert not g.on
    s.now+=26;c.tick();assert g.on and u.on
    assert False not in u.calls


@pytest.mark.parametrize('reading',[None,float('nan'),-1,126])
def test_bad_temperature_restores_gpio_without_interrupting_usb(wiring,reading):
    c,u,g,s=wiring;q=qualified(wiring);s.now+=60
    c.request(packet(mode='automatic',qualified=q));assert not g.on
    s.temperature=reading;c.tick();assert g.on and u.on


def test_probe_restores_even_without_browser_and_update_cancels_it(wiring):
    c,u,g,s=wiring
    c.request(packet('probe',ack=True));assert not g.on and u.on
    s.now=5;c.tick();assert g.on and c.gpio.status()['probe']=='confirm'
    c.request(packet('probe',ack=True));s.updating=True;c.tick()
    assert g.on and u.on and c.gpio.status()['probe']=='idle'
    with pytest.raises(FanError):c.request(packet('confirm',ack=True))
    with pytest.raises(FanError):c.request(packet('probe',ack=True))


def test_neither_old_usb_qualification_nor_gpio_fault_can_enable_fan_off(wiring):
    c,u,g,s=wiring;s.now=120
    result=c.request(packet(mode='automatic',qualified=u.fingerprint))
    assert g.on and not result['qualified']
    q=qualified(wiring);s.now+=60;g.fail=True
    result=c.request(packet(mode='automatic',qualified=q))
    assert result['fault'] and not result['qualified'] and g.on and u.on
    g.fail=False;c.request(packet('probe',ack=True))
    assert g.closed and not g.on and u.on


def test_migration_from_latched_usb_off_fault_and_back_starts_on(wiring):
    c,u,g,s=wiring
    c.usb.request(packet(backend='usb'));c.usb.fault=True
    result=c.request(packet('keep_on'))
    assert result['available'] and g.on and u.on
    q=qualified(wiring);s.now+=60;c.request(packet(mode='automatic',qualified=q));assert not g.on
    result=c.request(packet('keep_on',backend='usb'))
    assert g.on and u.on and result['backend']=='usb' and not result['qualified']


def test_usb_loss_prevents_gpio_off_and_repeated_poll_does_not_rewrite_usb(wiring):
    c,u,g,s=wiring;q=qualified(wiring);calls=list(u.calls)
    for _ in range(10):c.request(packet());c.tick()
    assert u.calls==calls
    c.usb.on=None;c.usb.power=None;c.usb.retry_at=10000
    result=c.request(packet(mode='automatic',qualified=q))
    assert not result['available'] and not result['qualified'] and g.on


def test_broker_restart_starts_gpio_on_then_resumes_saved_thermal_policy(wiring):
    c,u,g,s=wiring;q=qualified(wiring);s.now+=60
    c.request(packet(mode='automatic',qualified=q));assert not g.on
    c.close();assert g.on and u.on
    new_usb,new_board=Power(),Board()
    usb=USBFanController(lambda:new_usb,lambda:{'celsius':s.temperature},
        lambda:True,lambda:False,lambda:s.now,network=lambda:True)
    gpio=hw.GPIOFanController(lambda:new_board,temperature=lambda:{'celsius':s.temperature},
        updating=lambda:False,clock=lambda:s.now)
    fresh=hw.FanController(usb,gpio)
    result=fresh.request(packet(mode='automatic',qualified=q))
    assert result['qualified'] and new_board.on and new_usb.on
    s.now+=60;fresh.request(packet(mode='automatic',qualified=q))
    assert not new_board.on and new_usb.on and False not in new_usb.calls


def test_hub_off_is_restored_before_gpio_claim(wiring):
    c,u,g,s=wiring;s.storage=False;s.network=False
    c.request(packet('probe',backend='usb',ack=True));s.now=5;c.tick()
    q=c.request(packet('confirm',backend='usb',ack=True))['qualified_topology']
    s.now+=60;c.request(packet(backend='usb',mode='automatic',qualified=q));assert not u.on
    def factory():
        assert u.on  # Never initialize GPIO while its USB supply is off.
        return g
    c.gpio.factory=factory
    result=c.request(packet('keep_on'))
    assert result['backend']=='gpio12' and g.on and u.on


@pytest.mark.parametrize('extra',[{'backend':'gpio17'},{'backend':12},{'backend':[]},
    {'pin':12},{'path':'/dev/gpiochip0'},{'polarity':'active_low'},{'pwm':255}])
def test_root_wire_cannot_select_other_pins_paths_polarity_or_pwm(wiring,extra):
    c,u,g,s=wiring
    with pytest.raises(FanError):c.request({**packet(),**extra})
    assert g.calls==[] and u.calls==[]


@pytest.fixture
def gpio_kernel(tmp_path,monkeypatch):
    if sys.platform!='linux':
        pytest.skip('Linux GPIO character-device interface.')
    model=tmp_path/'model';model.write_bytes(b'Raspberry Pi 4 Model B Rev 1.4\0')
    dev=tmp_path/'dev';dev.mkdir();(dev/'gpiochip0').touch()
    state=SimpleNamespace(value=1,fd=None,chip=None,calls=[],busy=False,label=b'pinctrl-bcm2711',line=b'GPIO12')
    real_fstat=os.fstat
    state.real_fstat=real_fstat
    def fstat(fd):
        info=real_fstat(fd)
        return SimpleNamespace(st_mode=stat.S_IFCHR,st_rdev=0xFE00) if fd==state.chip else info
    def ioctl(fd,operation,data):
        state.calls.append(operation)
        if operation==hw.CHIP_INFO:
            state.chip=fd
            data[:]=struct.pack('=32s32sI',b'gpiochip0',state.label,58)
        elif operation==hw.LINE_INFO:
            assert len(data)==256 and struct.unpack_from('=I',data,64)[0]==12
            data[:len(state.line)]=state.line
            struct.pack_into('=Q',data,72,1 if state.busy else 0)
        elif operation==hw.GET_LINE:
            assert len(data)==592
            assert struct.unpack_from('=I',data)[0]==12
            assert data[4:256]==bytes(252)
            assert data[256:288].rstrip(b'\0')==b'luma-fan-bcm12'
            assert struct.unpack_from('=Q',data,288)[0]==8
            assert struct.unpack_from('=I',data,296)[0]==1
            assert struct.unpack_from('=IIQQ',data,320)==(2,0,1,1)
            assert struct.unpack_from('=I',data,560)[0]==1
            state.fd=os.dup(fd);struct.pack_into('=i',data,588,state.fd)
        elif operation in {hw.GET_VALUES,hw.SET_VALUES}:
            assert fd==state.fd and len(data)==16
            bits,mask=struct.unpack('=QQ',data);assert mask==1
            if operation==hw.SET_VALUES:
                assert bits in (0,1);state.value=bits
            else:struct.pack_into('=Q',data,0,state.value)
        else:raise AssertionError(operation)
    real_open=os.open
    def opened(path,flags):
        fd=real_open(path,flags);state.chip=fd;return fd
    monkeypatch.setattr(hw.os,'open',opened)
    monkeypatch.setattr(hw.os,'fstat',fstat)
    monkeypatch.setattr(hw,'_ioctl',ioctl)
    return dev,model,state


def test_gpio_abi_atomic_initial_on_readback_and_descriptor_cleanup(gpio_kernel):
    dev,model,s=gpio_kernel;p=hw.LinuxGPIOPower(dev,model)
    assert p.power_state() and len(p.fingerprint)==64
    assert not os.get_inheritable(p.fd)
    p.set_power(False);assert not p.power_state()
    p.set_power(True);assert p.power_state()
    fd=p.fd;p.close();assert p.fd is None and s.value==1
    with pytest.raises(OSError):os.fstat(fd)


@pytest.mark.parametrize('change',['busy','identity','label','model'])
def test_gpio_identity_or_busy_line_is_never_overridden(gpio_kernel,change):
    dev,model,s=gpio_kernel
    if change=='busy':s.busy=True
    if change=='identity':s.line=b'GPIO18'
    if change=='label':s.label=b'raspberrypi-exp-gpio'
    if change=='model':model.write_bytes(b'Raspberry Pi 5 Model B\0')
    with pytest.raises(FanError):hw.LinuxGPIOPower(dev,model)
    assert hw.GET_LINE not in s.calls and s.fd is None


@pytest.mark.parametrize('failure',['regular','symlink','request','readback'])
def test_gpio_rejects_unsafe_nodes_and_closes_failed_requests(gpio_kernel,monkeypatch,failure):
    dev,model,s=gpio_kernel
    original=hw._ioctl
    if failure=='regular':monkeypatch.setattr(hw.os,'fstat',s.real_fstat)
    if failure=='symlink':
        (dev/'gpiochip0').unlink();(dev/'gpiochip0').symlink_to(model)
    def ioctl(fd,operation,data):
        if operation==hw.GET_LINE and failure=='request':raise OSError('Synthetic EBUSY')
        original(fd,operation,data)
        if operation==hw.GET_VALUES and failure=='readback':struct.pack_into('=Q',data,0,0)
    monkeypatch.setattr(hw,'_ioctl',ioctl)
    with pytest.raises((FanError,OSError)):hw.LinuxGPIOPower(dev,model)
    for fd in (s.chip,s.fd):
        if fd is not None:
            with pytest.raises(OSError):s.real_fstat(fd)


def test_packed_gpio_requests_match_the_installed_linux_uapi(tmp_path):
    if sys.platform!='linux' or not shutil.which('cc') or not Path('/usr/include/linux/gpio.h').exists():
        pytest.skip('Linux UAPI compiler check; no GPIO device is needed.')
    source=tmp_path/'abi.c';binary=tmp_path/'abi'
    source.write_text('''#include <linux/gpio.h>
#include <stddef.h>
#include <stdio.h>
int main(void) {
 printf("%lu %lu %lu %lu %lu %zu %zu %zu %zu %zu %zu\\n",
 (unsigned long)GPIO_GET_CHIPINFO_IOCTL,(unsigned long)GPIO_V2_GET_LINEINFO_IOCTL,
 (unsigned long)GPIO_V2_GET_LINE_IOCTL,(unsigned long)GPIO_V2_LINE_GET_VALUES_IOCTL,
 (unsigned long)GPIO_V2_LINE_SET_VALUES_IOCTL,sizeof(struct gpio_v2_line_request),
 offsetof(struct gpio_v2_line_request,consumer),offsetof(struct gpio_v2_line_request,config),
 offsetof(struct gpio_v2_line_request,num_lines),offsetof(struct gpio_v2_line_request,fd),
 offsetof(struct gpio_v2_line_request,config)+offsetof(struct gpio_v2_line_config,attrs));
 return 0;
}''')
    subprocess.run(['cc','-Wall','-Werror',str(source),'-o',str(binary)],check=True,capture_output=True,timeout=20)
    result=subprocess.run([str(binary)],check=True,capture_output=True,text=True,timeout=5)
    assert list(map(int,result.stdout.split()))==[
        hw.CHIP_INFO,hw.LINE_INFO,hw.GET_LINE,hw.GET_VALUES,hw.SET_VALUES,592,256,288,560,588,320]
