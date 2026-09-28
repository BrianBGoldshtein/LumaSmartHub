"""USB-only Linux LIRC child worker. No shell, GPIO, paths from the caller or retries.

Executed by the Unix broker in a killable, deadline-bounded child process. ABI
constants are the Linux generic ioctl ABI used by Pi ARM64 and build-host x86_64.
See docs/IR_DEVICES.md for authoritative kernel references and hardware gates.
"""
from contextlib import suppress
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import select
import stat
import struct
import sys
import time

from .ir_signal import Frame, InfraredError, carrier, signal

MAX_WIRE = 16384
ID = re.compile(r'usb-ir-[a-f0-9]{24}')
GET_FEATURES = 0x80046900
GET_REC_MODE = 0x80046902
SET_SEND_MODE = 0x40046911
SET_REC_MODE = 0x40046912
SET_CARRIER = 0x40046913
SET_MASK = 0x40046917
SET_TIMEOUT_REPORTS = 0x40046919
SET_MEASURE = 0x4004691D
CAN_SEND = 0x2
CAN_CARRIER = 0x100
CAN_MASK = 0x400
CAN_RECEIVE = 0x40000
CAN_MEASURE = 0x02000000


def validate_request(value):
    if not isinstance(value, dict): raise InfraredError('Invalid infrared operation.')
    action = value.get('action')
    expected = {'discover': {'action'}, 'learn': {'action', 'device_id', 'carrier_hz'},
                'send': {'action', 'device_id', 'emitter', 'signal'}}
    if not isinstance(action, str) or action not in expected or set(value) != expected[action]:
        raise InfraredError('Invalid infrared operation.')
    if action == 'discover': return dict(value)
    if not isinstance(value['device_id'], str) or not ID.fullmatch(value['device_id']):
        raise InfraredError('Choose a discovered USB infrared adapter.')
    if action == 'learn':
        return {**value, 'carrier_hz': carrier(value['carrier_hz'], optional=True)}
    if value['emitter'] is not None and (type(value['emitter']) is not int or not 1 <= value['emitter'] <= 32):
        raise InfraredError('Choose one supported emitter channel.')
    return {**value, 'signal': signal(value['signal'])}


def ioctl_word(fd, request, value=0):
    import fcntl
    word = bytearray(struct.pack('=I', value))
    result = fcntl.ioctl(fd, request, word, True)
    return result, struct.unpack('=I', word)[0]


def _attribute(path, limit=200):
    with path.open('r', encoding='utf-8') as handle:
        value = handle.read(limit + 1).strip()
    if len(value) > limit or re.search(r'[\x00-\x1f\x7f]', value): raise ValueError()
    return value


def usb_identity(resolved, devices_root=Path('/sys/devices')):
    """Stable USB port + vendor/product + optional serial + interface, not rcN."""
    resolved = Path(resolved).resolve(strict=True)
    root = Path(devices_root).resolve(strict=True)
    if not resolved.is_relative_to(root): raise InfraredError('Not a USB infrared adapter.')
    interface = None
    for parent in (resolved, *resolved.parents):
        if parent == root: break
        if (parent / 'bInterfaceNumber').is_file(): interface = _attribute(parent / 'bInterfaceNumber', 8)
        if (parent / 'idVendor').is_file() and (parent / 'idProduct').is_file():
            vendor, product = _attribute(parent / 'idVendor', 4), _attribute(parent / 'idProduct', 4)
            if not re.fullmatch('[0-9a-fA-F]{4}', vendor) or not re.fullmatch('[0-9a-fA-F]{4}', product): raise ValueError()
            # Non-USB sysfs nodes cannot pass just by having similarly named files.
            if (parent / 'subsystem').resolve(strict=True).name != 'usb': raise ValueError()
            serial = _attribute(parent / 'serial') if (parent / 'serial').is_file() else ''
            identity = [str(parent.relative_to(root)), vendor.lower(), product.lower(), serial, interface]
            name = _attribute(parent / 'product') if (parent / 'product').is_file() else f'USB IR {vendor}:{product}'
            return identity, name[:100], bool(serial)
    raise InfraredError('Only USB infrared adapters are supported. GPIO is reserved for the microphone.')


def scan(sys_class=Path('/sys/class/lirc'), dev_root=Path('/dev'), devices_root=Path('/sys/devices')):
    if sys.platform != 'linux' or platform.machine().lower() not in ('aarch64', 'arm64', 'x86_64', 'amd64'):
        return []
    entries = []
    for node in sorted(Path(sys_class).glob('lirc*'))[:16]:
        if not re.fullmatch(r'lirc[0-9]{1,3}', node.name): continue
        fd = None
        try:
            identity, name, serial = usb_identity(node, devices_root)
            major, minor = (int(part) for part in _attribute(node / 'dev', 20).split(':'))
            path = Path(dev_root) / node.name
            fd = os.open(path, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW)
            info = os.fstat(fd)
            if not stat.S_ISCHR(info.st_mode) or info.st_rdev != os.makedev(major, minor): continue
            _, features = ioctl_word(fd, GET_FEATURES)
            receive, send = bool(features & CAN_RECEIVE), bool(features & CAN_SEND and features & CAN_CARRIER)
            if not (receive or send): continue
            # Includes interface and capabilities; ambiguous identical nodes are
            # removed below instead of being arbitrarily bound to a different fd.
            key = 'usb-ir-' + hashlib.sha256(json.dumps([identity, features], separators=(',', ':')).encode()).hexdigest()[:24]
            entries.append({'id': key, 'name': name, 'serial_present': serial, 'receive': receive, 'send': send,
                            'measure_carrier': bool(features & CAN_MEASURE), 'emitter_selection': bool(features & CAN_MASK),
                            '_path': str(path), '_rdev': info.st_rdev, '_features': features,
                            '_sysnode': str(node), '_devices_root': str(devices_root), '_identity': identity})
        except (OSError, ValueError):
            continue
        finally:
            if fd is not None: os.close(fd)
    counts = {entry['id']: sum(row['id'] == entry['id'] for row in entries) for entry in entries}
    return [entry for entry in entries if counts[entry['id']] == 1]


def public_devices(entries):
    return [{key: value for key, value in entry.items() if not key.startswith('_')} for entry in entries]


def open_checked(entry):
    fd = os.open(entry['_path'], os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISCHR(info.st_mode) or info.st_rdev != entry['_rdev']:
            raise InfraredError('Infrared adapter changed. Discover devices again.')
        _, features = ioctl_word(fd, GET_FEATURES)
        if features != entry['_features']: raise InfraredError('Infrared capabilities changed. Discover again.')
        identity, _, _ = usb_identity(Path(entry['_sysnode']), Path(entry['_devices_root']))
        if identity != entry['_identity']:
            raise InfraredError('Infrared adapter changed. Discover devices again.')
        return fd
    except BaseException:
        os.close(fd)
        raise


def learn(entry, fallback):
    if not entry['receive']: raise InfraredError('This adapter cannot receive raw IR.')
    if fallback is None and not entry['measure_carrier']:
        raise InfraredError('This receiver needs the remote carrier from its documentation, or a measuring receiver.')
    fd = open_checked(entry)
    previous = None
    measuring = False
    try:
        _, previous = ioctl_word(fd, GET_REC_MODE)
        ioctl_word(fd, SET_REC_MODE, 4)
        if entry['measure_carrier']:
            ioctl_word(fd, SET_MEASURE, 1)
            measuring = True
        # Require a real long space/timeout marker, not a userspace silence guess:
        # USB disconnection or a truncated buffer must not become a learned key.
        with suppress(OSError): ioctl_word(fd, SET_TIMEOUT_REPORTS, 1)
        # Discard data already queued before arming, bounded even under IR noise.
        for _ in range(8):
            try:
                stale = os.read(fd, 4096)
            except BlockingIOError:
                break
            if not stale: raise InfraredError('Infrared receiver disconnected.')
        else:
            raise InfraredError('IR receiver is busy. Release the remote button and try again.')
        frame = Frame(fallback)
        deadline = time.monotonic() + 10
        total_bytes = 0
        while time.monotonic() < deadline:
            readable, _, _ = select.select([fd], [], [], min(.1, max(0, deadline - time.monotonic())))
            if not readable:
                continue
            try:
                data = os.read(fd, 4096)
            except BlockingIOError:
                continue
            total_bytes += len(data)
            if not data or len(data) % 4 or total_bytes > 16384:
                raise InfraredError('IR capture was incomplete or noisy. Record one button again.')
            for (word,) in struct.iter_unpack('=I', data):
                frame.feed(word)
                if frame.complete: return frame.result()
        raise InfraredError('No complete button press within ten seconds. Try again.')
    finally:
        if measuring:
            with suppress(OSError): ioctl_word(fd, SET_MEASURE, 0)
        if previous is not None:
            with suppress(OSError): ioctl_word(fd, SET_REC_MODE, previous)
        os.close(fd)


def transmit(entry, emitter, raw):
    clean = signal(raw)
    if not entry['send']: raise InfraredError('This USB adapter cannot send with a selected carrier.')
    if entry['emitter_selection'] != (emitter is not None):
        raise InfraredError('Select exactly one emitter for this adapter, or use its single output.')
    fd = open_checked(entry)
    attempted = False
    try:
        ioctl_word(fd, SET_SEND_MODE, 2)
        ioctl_word(fd, SET_CARRIER, clean['carrier_hz'])
        if emitter is not None:
            result, _ = ioctl_word(fd, SET_MASK, 1 << (emitter - 1))
            if result != 0: raise InfraredError('That emitter channel is not supported. Nothing was sent.')
        payload = struct.pack(f'={len(clean["durations"])}I', *clean['durations'])
        attempted = True
        written = os.write(fd, payload)  # Exactly ONE syscall; partial/unknown sends never retried.
        if written != len(payload): raise OSError()
        return {'status': 'sent_unconfirmed', 'message': 'Command sent; IR device state is unconfirmed.'}
    except OSError:
        if attempted: return {'status': 'unknown', 'message': 'IR outcome is unknown. It will not be retried.'}
        raise InfraredError('IR setup failed before transmission. Nothing was sent.') from None
    finally:
        os.close(fd)


def execute(request):
    request = validate_request(request)
    entries = scan()
    if request['action'] == 'discover': return {'devices': public_devices(entries)}
    entry = next((entry for entry in entries if entry['id'] == request['device_id']), None)
    if not entry: raise InfraredError('USB infrared adapter is unavailable. Discover devices again.')
    if request['action'] == 'learn': return {'signal': learn(entry, request['carrier_hz'])}
    return transmit(entry, request['emitter'], request['signal'])


def main():
    try:
        raw = sys.stdin.buffer.readline(MAX_WIRE + 1)
        if len(raw) > MAX_WIRE or not raw.endswith(b'\n'): raise InfraredError('Invalid infrared request.')
        from .ir_protocol import decode
        result = execute(decode(raw))
    except InfraredError as exc:
        result = {'error': str(exc)}
    except Exception:
        result = {'error': 'USB infrared operation failed. Check the adapter before trying again.'}
    sys.stdout.write(json.dumps(result) + '\n')


if __name__ == '__main__': main()
