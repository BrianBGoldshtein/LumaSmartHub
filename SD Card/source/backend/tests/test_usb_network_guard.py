from pathlib import Path
import pytest
from luma.usb_fan import usb_network_attached,FanError
from test_usb_fan import rig,request,cool_off


def test_usb_network_detection_includes_down_wifi_and_ethernet_not_builtin(tmp_path):
    net=tmp_path/'class/net';net.mkdir(parents=True)
    builtin=tmp_path/'devices/mmc/net/wlan0';builtin.mkdir(parents=True)
    (net/'wlan0').symlink_to(builtin,target_is_directory=True)
    assert not usb_network_attached(net)
    usb=tmp_path/'devices/usb1/1-1/net/wlan1';usb.mkdir(parents=True)
    (net/'wlan1').symlink_to(usb,target_is_directory=True)
    assert usb_network_attached(net)  # No carrier/operstate needed: idle still pins power.
    (net/'wlan1').unlink()
    (net/'enx001122').symlink_to(usb,target_is_directory=True)
    assert usb_network_attached(net)
    assert usb_network_attached(tmp_path/'missing')
    (net/'broken').symlink_to(tmp_path/'nonexistent',target_is_directory=True)
    (net/'enx001122').unlink();assert usb_network_attached(net)


def test_usb_adapter_restores_off_power_cancels_probe_and_blocks_new_test(rig):
    c,p,s=rig;q=cool_off(rig);s.network=True
    result=request(c,mode='automatic',qualified=q)
    assert p.on and 'network adapter' in result['reason'] and result['mode']=='automatic'
    before=len(p.calls)
    with pytest.raises(FanError):request(c,'probe',acknowledged=True)
    assert p.on and all(p.calls[before:])
    s.network=False
    request(c,'probe',acknowledged=True);assert not p.on
    s.network=True;c.tick()
    assert p.on and c.status()['probe']=='idle' and not c.status()['qualified']
