"""Opt-in, coarse Pi 4 USB cooling. No shell, caller paths or rapid PWM.

The existing root USB broker owns this controller. The API supplies a short
heartbeat; the independent broker watchdog restores power when it expires.
USB PORT_POWER requests are confined to the onboard VL805's two hub views.
Reported hub bits are not a measurement of fan RPM or physical USB voltage.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import stat
import struct
import threading
import time
from contextlib import contextmanager

from .thermal import read_temperature

log = logging.getLogger(__name__)
ON_C, OFF_C = 60, 50
MIN_ON, MAX_OFF, HEARTBEAT_TTL = 60, 60, 25
PROBE_SECONDS = 5


class FanError(ValueError):
    pass


def validate_fan_request(value):
    if (not isinstance(value, dict) or set(value) != {
            'action', 'operation', 'mode', 'qualified_topology', 'acknowledged'}
            or value['action'] != 'fan'
            or not isinstance(value['operation'], str)
            or value['operation'] not in {'poll', 'probe', 'confirm', 'keep_on'}
            or not isinstance(value['mode'], str)
            or value['mode'] not in {'always_on', 'automatic'}
            or type(value['acknowledged']) is not bool
            or (value['qualified_topology'] is not None and
                (not isinstance(value['qualified_topology'], str) or
                 not re.fullmatch(r'[a-f0-9]{64}', value['qualified_topology'])))):
        raise FanError('Invalid cooling request.')
    if value['operation'] in {'probe', 'confirm'} and not value['acknowledged']:
        raise FanError('Confirm the USB interruption before testing cooling.')
    return value


def _text(path: Path, size=64):
    with path.open('rb') as stream:
        value = stream.read(size + 1)
    if len(value) > size:
        raise FanError('Unsupported USB topology.')
    return value.decode('ascii').strip()


@dataclass(frozen=True)
class Hub:
    bus: int
    device: int
    usb3: bool


class LinuxUSBPower:
    """Discover only Pi 4 B onboard hubs, then issue bounded USB hub ioctls.

    This avoids installing an OS package in an application-only update. Do
    not generalize this into a USB proxy or expose these operations to HTTP.
    """
    def __init__(self, sys_usb=Path('/sys/bus/usb/devices'),
                 model=Path('/sys/firmware/devicetree/base/model'), dev_usb=Path('/dev/bus/usb')):
        self.sys_usb, self.model, self.dev_usb = sys_usb, model, dev_usb
        self.hubs = self._discover()
        self.fingerprint = hashlib.sha256(repr(self.hubs).encode()).hexdigest()

    def _controller(self, root):
        for ancestor in root.resolve(strict=True).parents:
            if (ancestor / 'vendor').exists() and (ancestor / 'device').exists():
                if (_text(ancestor / 'vendor') == '0x1106' and
                        _text(ancestor / 'device') == '0x3483'):
                    return ancestor
        return None

    def _hub(self, path, usb3):
        if _text(path / 'bDeviceClass') != '09' or _text(path / 'maxchild') != '4':
            raise FanError('Unsupported onboard USB hubs.')
        bus, device = int(_text(path / 'busnum')), int(_text(path / 'devnum'))
        if not 1 <= bus <= 255 or not 1 <= device <= 127:
            raise FanError('Unsupported USB address.')
        return Hub(bus, device, usb3)

    def _discover(self):
        if not self.model.read_bytes().startswith(b'Raspberry Pi 4 Model B'):
            raise FanError('Cooling switching supports Raspberry Pi 4 Model B only.')
        pairs = {}
        for root in self.sys_usb.iterdir():
            if not re.fullmatch(r'usb[0-9]+', root.name):
                continue
            controller = self._controller(root)
            if controller is None:
                continue
            if (_text(root / 'idVendor'), _text(root / 'idProduct')) == ('1d6b', '0003'):
                pairs.setdefault(controller, {})['usb3'] = self._hub(root, True)
            elif (_text(root / 'idVendor'), _text(root / 'idProduct')) == ('1d6b', '0002'):
                child = self.sys_usb / (root.name[3:] + '-1')
                if (_text(child / 'idVendor'), _text(child / 'idProduct')) == ('2109', '3431'):
                    if not child.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
                        raise FanError('Unsupported internal USB hub.')
                    pairs.setdefault(controller, {})['usb2'] = self._hub(child, False)
        if len(pairs) != 1 or set(next(iter(pairs.values()))) != {'usb2', 'usb3'}:
            raise FanError('Onboard USB switching is unavailable.')
        pair = next(iter(pairs.values()))
        return (pair['usb2'], pair['usb3'])

    def _transfer(self, hub, port, on=None):
        import fcntl  # Appliance-only; tests may run on Windows.
        node = self.dev_usb / f'{hub.bus:03}' / f'{hub.device:03}'
        descriptor = os.open(node, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            info = os.fstat(descriptor)
            expected_minor = (hub.bus - 1) * 128 + hub.device - 1
            if (not stat.S_ISCHR(info.st_mode) or os.major(info.st_rdev) != 189
                    or os.minor(info.st_rdev) != expected_minor):
                raise FanError('USB device identity changed.')
            data = ctypes.create_string_buffer(4)
            # Linux usbdevfs_ctrltransfer: native alignment, pointer width.
            body = struct.pack('@BBHHHIP', 0xa3 if on is None else 0x23,
                               0 if on is None else 3 if on else 1,
                               0 if on is None else 8, port,
                               4 if on is None else 0, 1000,
                               ctypes.addressof(data) if on is None else 0)
            ioctl = 0xc0005500 | (len(body) << 16)
            fcntl.ioctl(descriptor, ioctl, body)
            if on is None:
                bits, _ = struct.unpack('<HH', data.raw)
                return bool(bits & (0x200 if hub.usb3 else 0x100))
        finally:
            os.close(descriptor)

    def set_power(self, on):
        failed = False
        # Attempt every port even if one fails: restoration is best effort.
        for hub in self.hubs:
            for port in range(1, 5):
                try:
                    self._transfer(hub, port, on)
                except (OSError, ValueError):
                    failed = True
        if failed:
            raise FanError('USB power switching failed; keep USB powered.')
        if self.power_state() != on:
            raise FanError('USB hubs did not confirm the requested power state.')

    def power_state(self):
        values = [self._transfer(hub, port) for hub in self.hubs for port in range(1, 5)]
        if all(values):
            return True
        if not any(values):
            return False
        return None


def usb_storage_attached(usb=Path('/sys/bus/usb/devices'), blocks=Path('/sys/class/block')):
    """Fail closed, including unmounted, unformatted and USB-root disks."""
    try:
        for path in blocks.iterdir():
            if any(re.fullmatch(r'usb[0-9]+', part) for part in path.resolve(strict=True).parts):
                return True
        for path in usb.iterdir():
            field = path / 'bInterfaceClass'
            if field.exists() and _text(field) == '08':
                return True
        return False
    except (OSError, ValueError):
        return True


def update_in_progress(root=Path('/opt/luma-releases')):
    """Durable install state plus the updater's live exclusive lock."""
    try:
        import fcntl
        status = root / '.luma-update-status.json'
        if status.exists():
            with status.open('rb') as stream:
                raw = stream.read(16385)
            if len(raw) > 16384 or json.loads(raw).get('state') == 'installing':
                return True
        lock = root / '.luma-update.lock'
        if lock.exists():
            fd = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                fcntl.flock(fd, fcntl.LOCK_UN)
            except BlockingIOError:
                return True
            finally:
                os.close(fd)
        return False
    except (ImportError, OSError, ValueError, AttributeError):
        return True


class USBFanController:
    def __init__(self, power_factory=LinuxUSBPower, temperature=read_temperature,
                 storage=usb_storage_attached, updating=update_in_progress, clock=time.monotonic):
        self.factory, self.temperature, self.storage, self.updating, self.clock = (
            power_factory, temperature, storage, updating, clock)
        self.lock = threading.RLock()
        self.power = None
        self.mode, self.qualified = 'always_on', None
        self.last_seen = -math.inf
        self.on = None
        self.changed = self.clock()
        self.probe_until = None
        self.probe_completed = False
        self.media_busy, self.hold_until = 0, 0
        self.reason = 'Keep USB on'
        self.fault = False
        self.retry_at = 0

    def _switch(self, on):
        if self.on is on:
            return
        self.power.set_power(on)
        self.on, self.changed = on, self.clock()
        log.info('Cooling USB power %s', 'on' if on else 'off')

    def _restore(self):
        if self.power is None:
            return
        # Do not trust a cached on bit after any partially failed operation.
        self.on = None
        self._switch(True)

    def _guard(self):
        if self.media_busy or self.clock() < self.hold_until:
            return 'USB access in progress'
        if self.storage():
            return 'USB storage attached · power stays on'
        if self.updating():
            return 'Software update · power stays on'
        return None

    def _tick(self):
        now = self.clock()
        if self.power is None:
            if now < self.retry_at:
                return
            self.retry_at = now + 60
            self.power = self.factory()
            self.on = self.power.power_state()
            self._restore()
            self.fault = False
        elif self.power.power_state() is not self.on:
            # An outside change or partial switch must never leave cached
            # "on" status suppressing the independent restoration attempt.
            raise FanError('USB power state changed unexpectedly.')
        reason = self._guard()
        if self.fault:
            reason = 'Switching failed · automatic cooling disabled'
        if self.probe_until is not None:
            if now >= self.probe_until or reason or now - self.last_seen > HEARTBEAT_TTL:
                self._switch(True)
                self.probe_completed = not reason and now - self.last_seen <= HEARTBEAT_TTL
                self.probe_until = None
                self.reason = 'Test restored USB power · confirm fan stopped and restarted' if self.probe_completed else 'Test cancelled · USB power restored'
            else:
                self.reason = 'Testing · USB power returns within 5 seconds'
            return
        if not reason and now - self.last_seen > HEARTBEAT_TTL:
            reason = 'Controller heartbeat expired · power stays on'
        if not reason and (self.mode != 'automatic' or self.qualified != self.power.fingerprint):
            reason = 'Keep USB on' if self.mode == 'always_on' else 'Run and confirm the USB test first'
        if reason:
            self._switch(True)
            self.reason = reason
            return
        reading = self.temperature().get('celsius')
        if (type(reading) not in {float, int} or not math.isfinite(reading)
                or not 0 < reading <= 125):
            self._switch(True)
            self.reason = 'Temperature unavailable · power stays on'
        elif reading >= ON_C:
            self._switch(True)
            self.reason = 'Cooling · USB power on'
        elif self.on is False and now - self.changed >= MAX_OFF:
            self._switch(True)
            self.reason = 'USB discovery window · power on for at least 60 seconds'
        elif self.on is True and reading <= OFF_C and now - self.changed >= MIN_ON:
            self._switch(False)
            self.reason = 'Cool enough · USB power off for at most 60 seconds'
        else:
            self.reason = 'Cooling · USB power on' if self.on else 'Cool enough · USB power off for at most 60 seconds'

    def tick(self):
        with self.lock:
            try:
                self._tick()
            except (OSError, ValueError, RuntimeError):
                self.fault = True
                self.mode, self.qualified = 'always_on', None
                self.probe_until, self.probe_completed = None, False
                self.reason = 'USB switching unavailable · use the fan continuously'
                try:
                    self._restore()
                except (OSError, ValueError, RuntimeError):
                    self.on = None

    def status(self):
        return {'available': self.power is not None and not self.fault,
                'mode': self.mode, 'usb_power': 'on' if self.on is True else 'off' if self.on is False else 'unknown',
                'qualified': self.power is not None and self.qualified == self.power.fingerprint and not self.fault,
                'qualified_topology': self.qualified,
                'probe': 'running' if self.probe_until is not None else 'confirm' if self.probe_completed else 'idle',
                'reason': self.reason, 'on_celsius': ON_C, 'off_celsius': OFF_C,
                'max_off_seconds': MAX_OFF}

    def request(self, value):
        validate_fan_request(value)
        with self.lock:
            self.last_seen = self.clock()
            # Always-on is an immediate override, including during a test.
            if value['operation'] == 'keep_on':
                self.probe_until = None
                self.probe_completed = False
                self._restore()
            if value['operation'] == 'probe' and self.fault:
                self.power = None
                self.retry_at = 0
            self.mode, self.qualified = value['mode'], value['qualified_topology']
            self.tick()
            operation = value['operation']
            if operation == 'probe':
                if self.power is None or self.fault or self._guard():
                    raise FanError('Test unavailable. Remove USB drives, finish updates and check the Pi.')
                self.mode, self.qualified = 'always_on', None
                self.probe_completed = False
                try:
                    self._switch(False)
                    self.probe_until = self.clock() + PROBE_SECONDS
                except (OSError, ValueError, RuntimeError):
                    self.fault = True
                    self._restore()
                    raise FanError('USB test failed; automatic cooling remains disabled.') from None
            elif operation == 'confirm':
                if not self.probe_completed or self.probe_until is not None or self.on is not True or self.fault:
                    raise FanError('Run the USB test and wait for power to return first.')
                self.qualified = self.power.fingerprint
                self.probe_completed = False
            return self.status()

    @contextmanager
    def media_access(self):
        with self.lock:
            self.media_busy += 1
            self.tick()
            if self.power is not None and self.on is not True:
                self.media_busy -= 1
                raise FanError('Restore USB power before accessing a drive.')
        try:
            yield
        finally:
            with self.lock:
                self.media_busy -= 1
                self.hold_until = self.clock() + MIN_ON

    def close(self):
        with self.lock:
            self.mode = 'always_on'
            try:
                self._restore()
            except (OSError, ValueError, RuntimeError):
                log.error('Cooling shutdown could not confirm USB power restoration')
