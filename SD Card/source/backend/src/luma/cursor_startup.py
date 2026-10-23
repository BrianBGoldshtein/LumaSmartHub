"""Park the real Wayland pointer once per compositor session, without clicks.

Uses the existing wlroots virtual-pointer v1 protocol and Python stdlib only.
No uinput/root access, packages, keyboard injection or compositor config edits.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import socket
import stat
import struct
import tempfile
import time


MANAGER = 'zwlr_virtual_pointer_manager_v1'
U32 = struct.Struct('=I')
HEADER = struct.Struct('=II')


def _uints(*values):
    return struct.pack('=' + 'I' * len(values), *values)


def _string(value):
    encoded = value.encode('utf-8') + b'\0'
    return U32.pack(len(encoded)) + encoded + bytes((-len(encoded)) % 4)


class _WaylandPointer:
    """Minimal bounded client; never requests keyboard, button or scroll input."""
    def __init__(self, path, timeout=2.):
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.deadline = time.monotonic() + timeout
        self.next_id = 3
        self.buffer = bytearray()
        self.globals = {}
        try:
            self.socket.settimeout(timeout)
            self.socket.connect(str(path))
            self.send(1, 1, _uints(2))  # wl_display.get_registry
            self.roundtrip()
        except BaseException:
            self.close()
            raise

    def close(self):
        self.socket.close()

    def allocate(self):
        value = self.next_id
        self.next_id += 1
        return value

    def send(self, sender, opcode, payload=b''):
        self.socket.settimeout(max(.001, self.deadline - time.monotonic()))
        self.socket.sendall(HEADER.pack(sender, ((len(payload) + 8) << 16) | opcode) + payload)

    def event(self):
        while True:
            if len(self.buffer) >= 8:
                sender, word = HEADER.unpack_from(self.buffer)
                size, opcode = word >> 16, word & 0xffff
                if size < 8 or size % 4 or size > 65532:
                    raise ValueError('Invalid Wayland event')
                if len(self.buffer) >= size:
                    payload = bytes(self.buffer[8:size])
                    del self.buffer[:size]
                    return sender, opcode, payload
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Wayland cursor request timed out')
            self.socket.settimeout(remaining)
            data = self.socket.recv(65536)
            if not data or len(self.buffer) + len(data) > 131072:
                raise ValueError('Wayland connection unavailable')
            self.buffer.extend(data)

    def roundtrip(self):
        callback = self.allocate()
        self.send(1, 0, _uints(callback))  # wl_display.sync
        while True:
            sender, opcode, payload = self.event()
            if sender == 1 and opcode == 0:
                # Do not log compositor errors, which can contain private paths.
                raise ValueError('Wayland cursor request rejected')
            if sender == callback and opcode == 0:
                return
            if sender == 2 and opcode == 0:
                if len(payload) < 12:
                    raise ValueError('Invalid Wayland global')
                name, length = struct.unpack_from('=II', payload)
                end = 8 + length
                padded = 8 + ((length + 3) // 4) * 4
                if not 1 <= length <= 256 or padded + 4 != len(payload) or payload[end-1] != 0:
                    raise ValueError('Invalid Wayland global')
                interface = payload[8:end-1].decode('utf-8')
                version = U32.unpack_from(payload, padded)[0]
                self.globals[interface] = (name, version)

    def park(self):
        manager, pointer = self.pointer()
        # Normalized 1.0, 1.0 reaches the compositor's last addressable pixel,
        # independent of resolution, scale or orientation. No inset/margin.
        self.send(pointer, 1, _uints(int(time.monotonic()*1000) & 0xffffffff, 1, 1, 1, 1))
        self.send(pointer, 4)  # Frame commits the motion.
        self.roundtrip()
        self.finish(manager, pointer)

    def pointer(self):
        name, version = self.globals.get(MANAGER, (0, 0))
        if not name or version < 1:
            raise ValueError('Wayland virtual pointer unavailable')
        manager, pointer = self.allocate(), self.allocate()
        self.send(2, 0, _uints(name) + _string(MANAGER) + _uints(1, manager))
        self.send(manager, 0, _uints(0, pointer))  # Default seat, create pointer.
        return manager, pointer

    def finish(self, manager, pointer):
        self.send(pointer, 8)  # Destroy the temporary input device.
        self.send(manager, 1)
        self.roundtrip()

    def refresh(self):
        manager, pointer = self.pointer()
        # Wayland Chromium can retain an old cursor image after CSS changes.
        # A zero motion is discarded by wlroots. One 24.8 fixed-point unit
        # (1/256 pixel), then its inverse, refreshes it without a visible move.
        # No clicks, keys, scrolling or full-pixel relocation are generated.
        for dx in (1, -1):
            self.send(pointer, 0, struct.pack('=Iii', int(time.monotonic()*1000) & 0xffffffff, dx, 0))
            self.send(pointer, 4)
            self.roundtrip()
        self.finish(manager, pointer)


def park_pointer(path: Path):
    connection = _WaylandPointer(path)
    try:
        connection.park()
    finally:
        connection.close()


def refresh_pointer(path: Path):
    connection = _WaylandPointer(path)
    try:
        connection.refresh()
    finally:
        connection.close()


def _endpoint(env):
    runtime = Path(env['XDG_RUNTIME_DIR'])
    if not runtime.is_absolute():
        raise ValueError('Private graphical runtime unavailable')
    directory = runtime.lstat()
    if not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.getuid() or directory.st_mode & 0o077:
        raise ValueError('Private graphical runtime unavailable')
    name = env['WAYLAND_DISPLAY']
    path = Path(name)
    if not path.is_absolute():
        if path.name != name or not name:
            raise ValueError('Invalid graphical socket')
        path = runtime / name
    if path.parent != runtime:
        raise ValueError('Graphical socket outside private runtime')
    info = path.lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError('Graphical socket unavailable')
    identity = f'{info.st_dev}:{info.st_ino}:{info.st_ctime_ns}'
    marker = runtime / ('luma-cursor-park-' + hashlib.sha256(name.encode()).hexdigest()[:16])
    return path, identity, marker


class StartupCursor:
    def __init__(self, *, env=None, clock=time.monotonic, park=park_pointer):
        self.env = os.environ if env is None else env
        self.clock, self.park = clock, park
        self.next_try = 0.
        self.identity = None
        self.status = 'unavailable; retrying'

    def tick(self):
        if self.clock() < self.next_try:
            return self.status
        self.next_try = self.clock() + 5
        try:
            path, identity, marker = _endpoint(self.env)
            if identity == self.identity:
                self.status = 'ok'
                return self.status
            if marker.exists() or marker.is_symlink():
                info = marker.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > 128:
                    raise ValueError('Unsafe cursor marker')
                if marker.read_text() == identity:
                    self.identity, self.status = identity, 'ok'
                    return self.status
            self.park(path)
            if _endpoint(self.env)[1] != identity:
                raise ValueError('Graphical session changed during startup')
            # Atomic private marker survives a bridge restart, not a reboot.
            fd, temporary = tempfile.mkstemp(prefix='.luma-cursor-', dir=marker.parent)
            try:
                with os.fdopen(fd, 'w') as output:
                    output.write(identity)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, marker)
            finally:
                Path(temporary).unlink(missing_ok=True)
            self.identity, self.status = identity, 'ok'
        except (KeyError, OSError, ValueError):
            self.status = 'unavailable; retrying'
        return self.status
