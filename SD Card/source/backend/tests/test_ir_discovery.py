"""Synthetic Linux sysfs/device metadata; no real device access."""
from pathlib import Path
import os
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest

from luma import ir_linux as linux
from luma.ir_protocol import decode

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Linux sysfs/symlink contract')


@pytest.fixture
def tree(tmp_path, monkeypatch):
    devices = tmp_path / 'sys/devices'
    usb = devices / 'platform/usb1/1-2'
    interface = usb / '1-2:1.0'
    node = interface / 'rc/rc0/lirc0'
    node.mkdir(parents=True)
    bus = tmp_path / 'sys/bus/usb'
    bus.mkdir(parents=True)
    (usb / 'subsystem').symlink_to(bus)
    for name, value in {'idVendor': '1234', 'idProduct': 'abcd', 'serial': 'test serial', 'product': 'Test USB IR'}.items():
        (usb / name).write_text(value)
    (interface / 'bInterfaceNumber').write_text('00')
    (node / 'dev').write_text('240:0')
    sys_class = tmp_path / 'sys/class/lirc'
    sys_class.mkdir(parents=True)
    (sys_class / 'lirc0').symlink_to(node)
    dev = tmp_path / 'dev'
    dev.mkdir()
    state = SimpleNamespace(mode=stat.S_IFCHR, rdev=os.makedev(240, 0), features=(linux.CAN_SEND | linux.CAN_CARRIER |
                            linux.CAN_RECEIVE | linux.CAN_MASK), opened=[], closed=[])
    def opened(path, flags):
        assert path == dev / 'lirc0' or path == dev / 'lirc1'
        assert flags & os.O_NOFOLLOW and flags & os.O_NONBLOCK
        state.opened.append(path)
        return 42
    monkeypatch.setattr(linux.os, 'open', opened)
    monkeypatch.setattr(linux.os, 'fstat', lambda fd: SimpleNamespace(st_mode=state.mode, st_rdev=state.rdev))
    monkeypatch.setattr(linux.os, 'close', state.closed.append)
    monkeypatch.setattr(linux, 'ioctl_word', lambda fd, request: (0, state.features))
    return SimpleNamespace(usb=usb, interface=interface, node=node, sys_class=sys_class, dev=dev,
                           devices=devices, state=state, scan=lambda: linux.scan(sys_class, dev, devices))


def test_usb_identity_capabilities_and_public_redaction(tree):
    entry, = tree.scan()
    assert entry['send'] and entry['receive'] and entry['emitter_selection']
    assert entry['serial_present'] and not entry['measure_carrier']
    assert entry['id'].startswith('usb-ir-') and 'test serial' not in str(linux.public_devices([entry]))
    assert all(not key.startswith('_') for key in linux.public_devices([entry])[0])
    assert tree.state.closed == [42]
    (tree.usb / 'serial').write_text('replacement')
    changed, = tree.scan()
    assert changed['id'] != entry['id']


def test_gpio_regular_files_wrong_rdev_and_no_carrier_tx_are_rejected(tree):
    tree.state.mode = stat.S_IFREG
    assert tree.scan() == []
    tree.state.mode = stat.S_IFCHR
    tree.state.rdev = os.makedev(240, 2)
    assert tree.scan() == []
    tree.state.rdev = os.makedev(240, 0)
    tree.state.features = linux.CAN_SEND  # No carrier selection and no receiver.
    assert tree.scan() == []
    tree.state.features = linux.CAN_RECEIVE
    entry, = tree.scan()
    assert entry['receive'] and not entry['send']
    (tree.usb / 'idVendor').unlink()
    assert tree.scan() == []


def test_duplicate_indistinguishable_nodes_not_arbitrarily_selected(tree):
    second = tree.node.parent / 'lirc1'
    second.mkdir()
    (second / 'dev').write_text('240:0')
    (tree.sys_class / 'lirc1').symlink_to(second)
    assert tree.scan() == []
    assert tree.state.closed == [42, 42]


def test_symlink_escape_and_invalid_sysfs_attributes(tree, tmp_path):
    (tree.usb / 'product').write_text('bad\x00product')
    assert tree.scan() == []
    outside = tmp_path / 'outside'
    outside.mkdir()
    (tree.sys_class / 'lirc0').unlink()
    (tree.sys_class / 'lirc0').symlink_to(outside)
    assert tree.scan() == []


def test_installed_isolated_worker_rejects_input_before_discovery():
    result = subprocess.run([sys.executable, '-I', '-m', 'luma.ir_linux'],
                            input=b'{"action":"shell","secret":"do not echo"}\n',
                            capture_output=True, timeout=5, check=True)
    assert decode(result.stdout) == {'error': 'Invalid infrared operation.'}
    assert not result.stderr and b'do not echo' not in result.stdout
