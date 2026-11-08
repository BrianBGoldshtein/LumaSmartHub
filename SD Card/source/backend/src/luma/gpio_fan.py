"""Fixed BCM12 control for a 3.3 V active-high inline USB fan switch.

Motor current comes from USB, never from GPIO. The protected broker alone
owns the line. No caller can select a device path, offset, polarity or PWM.
Linux GPIO ABI v2 is used directly; no OS package or /dev/mem is needed.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat
import struct
import threading

from .usb_fan import FanError, USBFanController, validate_fan_request

CHIP_INFO = 0x8044b401
LINE_INFO = 0xc100b405
GET_LINE = 0xc250b407
GET_VALUES = 0xc010b40e
SET_VALUES = 0xc010b40f
BCM_LINE = 12  # Physical header pin 32, NOT physical pin 12 (I2S audio).


def _ioctl(fd, operation, value):
    import fcntl
    return fcntl.ioctl(fd, operation, value, True)


class LinuxGPIOPower:
    """Exclusive, atomic initially-high request of the Pi 4's BCM12 only."""
    def __init__(self, devices=Path('/dev'),
                 model=Path('/sys/firmware/devicetree/base/model')):
        self.fd = None
        if not model.read_bytes().startswith(b'Raspberry Pi 4 Model B'):
            raise FanError('GPIO fan switching supports Raspberry Pi 4 Model B only.')
        matches = []
        try:
            for path in devices.glob('gpiochip*'):
                if not re.fullmatch(r'gpiochip[0-9]+', path.name):
                    continue
                fd = os.open(path, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
                try:
                    info = os.fstat(fd)
                    if not stat.S_ISCHR(info.st_mode):
                        raise FanError('GPIO device identity is unavailable.')
                    data = bytearray(68)
                    _ioctl(fd, CHIP_INFO, data)
                    name, label, lines = struct.unpack('=32s32sI', data)
                    label = label.split(b'\0', 1)[0]
                    if label not in {b'pinctrl-bcm2711', b'pinctrl-bcm2835'}:
                        continue
                    if not 28 <= lines <= 64:
                        raise FanError('Unsupported GPIO controller.')
                    line = bytearray(256)
                    struct.pack_into('=I', line, 64, BCM_LINE)
                    _ioctl(fd, LINE_INFO, line)
                    if line[:32].split(b'\0', 1)[0] != b'GPIO12':
                        raise FanError('BCM12 identity could not be verified.')
                    if struct.unpack_from('=Q', line, 72)[0] & 1:
                        raise FanError('BCM12 is already used; keep the fan directly powered.')
                    matches.append((fd, label, info.st_rdev))
                    fd = None
                finally:
                    if fd is not None:
                        os.close(fd)
            if len(matches) != 1:
                raise FanError('One supported Pi GPIO controller is required.')
            chip, label, device = matches[0]
            # gpio_v2_line_request: 64 offsets, consumer[32], config[272],
            # num_lines, event_buffer_size, padding[5], returned fd = 592 B.
            request = bytearray(592)
            struct.pack_into('=I', request, 0, BCM_LINE)
            consumer = b'luma-fan-bcm12'
            request[256:256 + len(consumer)] = consumer
            struct.pack_into('=Q', request, 288, 1 << 3)  # OUTPUT, active high
            struct.pack_into('=I', request, 296, 1)  # one output-value attribute
            struct.pack_into('=IIQQ', request, 320, 2, 0, 1, 1)  # initially ON
            struct.pack_into('=I', request, 560, 1)
            struct.pack_into('=i', request, 588, -1)
            _ioctl(chip, GET_LINE, request)  # EBUSY is never overridden.
            self.fd = struct.unpack_from('=i', request, 588)[0]
            if self.fd < 0:
                self.fd = None
                raise FanError('GPIO line request failed.')
            os.set_inheritable(self.fd, False)
            self.fingerprint = hashlib.sha256(
                b'luma-8086-usb2-bcm12-active-high-v1:' + label + str(device).encode()).hexdigest()
            if not self.power_state():
                raise FanError('GPIO did not confirm fan-on control.')
        except BaseException:
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
            raise
        finally:
            for fd, _, _ in matches:
                os.close(fd)

    def power_state(self):
        values = bytearray(struct.pack('=QQ', 0, 1))
        _ioctl(self.fd, GET_VALUES, values)
        return bool(struct.unpack_from('=Q', values)[0] & 1)

    def set_power(self, on):
        values = bytearray(struct.pack('=QQ', int(on), 1))
        _ioctl(self.fd, SET_VALUES, values)
        if self.power_state() is not on:
            raise FanError('GPIO control readback failed.', code='power_unconfirmed')

    def close(self):
        if self.fd is not None:
            try:
                self.set_power(True)
            finally:
                os.close(self.fd)
                self.fd = None
        # On release/reboot a line is uncontrolled and this board defaults OFF.
        # This is not a hardware fail-on thermostat; document that explicitly.


class GPIOFanController(USBFanController):
    """Reuse the qualified 70/60 hysteresis, test and heartbeat watchdog.

    USB networking/storage cannot inhibit this separate fan output. Updates
    still hold the fan on. The outer coordinator independently keeps USB on.
    """
    def __init__(self, power_factory=LinuxGPIOPower, **kwargs):
        super().__init__(power_factory=power_factory, storage=lambda:False,
                         network=lambda:False, **kwargs)

    def status(self):
        result = super().status()
        result.update(backend='gpio12', fan_power=result['usb_power'],
                      usb_power='unknown', gpio_bcm=BCM_LINE)
        result['reason'] = result['reason'].replace('USB', 'fan').replace('Fan fan', 'Fan')
        return result

    def request(self, value):
        with self.lock:
            # A retry must release our old claim before asking the kernel for
            # a new one. Otherwise our own held fd would cause EBUSY forever.
            if value.get('operation') == 'probe' and self.fault and self.power is not None:
                if hasattr(self.power, 'close'):
                    try:
                        self.power.close()
                    except (OSError, ValueError):
                        pass
                self.power = None
            return super().request(value)

    def close(self):
        super().close()
        if self.power is not None and hasattr(self.power, 'close'):
            self.power.close()


class FanController:
    """Coordinate optional BCM12 switching without interrupting the USB hub."""
    def __init__(self, usb=None, gpio=None):
        self.usb = usb or USBFanController()
        self.gpio = gpio or GPIOFanController()
        self.backend = 'usb'
        self.lock = threading.RLock()

    def _usb_on(self):
        status = self.usb.status()
        operation = ('poll' if status.get('mode') == 'always_on'
                     and status.get('usb_power') == 'on' and status.get('probe') == 'idle'
                     else 'keep_on')
        result = self.usb.request({'action':'fan', 'operation':operation,
            'mode':'always_on', 'qualified_topology':None, 'acknowledged':False})
        # A latched "never switch this hub off" fault must not deadlock a
        # move to separate GPIO control when restoration confirmed ON.
        return result.get('usb_power') == 'on'

    def _gpio_on(self):
        return self.gpio.request({'action':'fan', 'operation':'keep_on',
            'mode':'always_on', 'qualified_topology':None, 'acknowledged':False})

    def _status(self, result):
        if self.backend == 'usb':
            return {**result, 'backend':'usb', 'fan_power':result['usb_power']}
        usb = self.usb.status()
        result = {**result, 'backend':'gpio12', 'usb_power':usb['usb_power']}
        if usb['usb_power'] != 'on':
            result.update(available=False, qualified=False, fault=True,
                          reason='USB supply unconfirmed · connect the fan directly to powered USB')
        return result

    def request(self, value):
        validate_fan_request(value)
        with self.lock:
            selected = value.get('backend', 'usb')
            if selected != self.backend:
                # Restore the whole hub BEFORE requesting GPIO or changing
                # wiring modes. Both qualifications must be tested afresh.
                if not self._usb_on():
                    raise FanError('Restore USB power before moving the fan control.')
                if self.backend == 'gpio12':
                    self._gpio_on()
                self.backend = selected
            packet = {k:v for k,v in value.items() if k != 'backend'}
            if self.backend == 'gpio12':
                if not self._usb_on():
                    return self._status(self._gpio_on())
                return self._status(self.gpio.request(packet))
            return self._status(self.usb.request(packet))

    def tick(self):
        with self.lock:
            self.usb.tick()
            if self.backend == 'gpio12':
                usb = self.usb.status()
                if usb['usb_power'] != 'on':
                    self._gpio_on()
                self.gpio.tick()

    def media_access(self):
        return self.usb.media_access()

    def status(self):
        with self.lock:
            return self._status((self.gpio if self.backend == 'gpio12' else self.usb).status())

    def close(self):
        with self.lock:
            try:
                self.gpio.close()
            finally:
                self.usb.close()
