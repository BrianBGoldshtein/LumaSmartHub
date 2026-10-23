"""Immediate private desktop cursor refresh, not a general input API."""
from __future__ import annotations

import os
from pathlib import Path
import socket
import stat
import struct
from threading import Event, Thread

from .cursor_startup import _endpoint, refresh_pointer

SOCKET_NAME = 'luma-cursor-refresh-v1.sock'


def _private_directory(path):
    directory = path.lstat()
    if (not path.is_absolute() or not stat.S_ISDIR(directory.st_mode)
            or directory.st_uid != os.getuid() or directory.st_mode & 0o077):
        raise ValueError('Private graphical runtime unavailable')


def notify_cursor_refresh(*, directory=None):
    """Fixed request only. Coordinates, commands and arbitrary input are absent."""
    try:
        if os.name != 'posix':
            return False
        directory = Path(directory) if directory is not None else Path(os.environ.get('LUMA_DATA_DIR','/var/lib/luma'))
        _private_directory(directory)
        endpoint = directory/SOCKET_NAME
        info = endpoint.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            return False
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            client.settimeout(1)
            client.connect(str(endpoint))
            client.sendall(b'R')
            return client.recv(1)==b'Y'
    except (OSError,ValueError):
        return False


class CursorRefreshServer:
    """Runs in the existing unprivileged graphical device bridge."""
    def __init__(self, *, env=None, refresh=refresh_pointer):
        self.env = os.environ if env is None else env
        self.refresh = refresh
        self.stop = Event()
        self.listener = self.thread = self.path = self.inode = None

    def __enter__(self):
        try:
            # The API has ProtectHome=true, which hides /run/user as well as
            # /home. Its existing private data directory is the shared IPC
            # location; only this graphical process opens the Wayland socket.
            directory = Path(self.env.get('LUMA_DATA_DIR','/var/lib/luma'))
            _private_directory(directory)
            self.path = directory/SOCKET_NAME
            if self.path.exists() or self.path.is_symlink():
                info = self.path.lstat()
                if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                    return self
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as probe:
                    probe.settimeout(.1)
                    try:
                        probe.connect(str(self.path))
                        return self  # Never replace a live helper.
                    except ConnectionRefusedError:
                        self.path.unlink()  # Only this private stale socket.
            self.listener = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            self.listener.bind(str(self.path))
            self.inode = self.path.stat().st_ino
            self.path.chmod(0o600)
            self.listener.listen(4)
            self.listener.settimeout(.2)
            self.thread = Thread(target=self.run,name='luma-cursor',daemon=True)
            self.thread.start()
        except (KeyError,OSError,ValueError):
            if self.listener: self.listener.close()
        return self

    def run(self):
        while not self.stop.is_set():
            try:
                client,_ = self.listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with client:
                try:
                    client.settimeout(.5)
                    _,uid,_ = struct.unpack('3i',client.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                    if uid!=os.getuid() or client.recv(8)!=b'R':
                        continue
                    path,_,_ = _endpoint(self.env)
                    self.refresh(path)
                    client.sendall(b'Y')
                except (OSError,ValueError):
                    # Never print paths or render input as a shell command.
                    continue

    def __exit__(self,*_):
        self.stop.set()
        if self.listener: self.listener.close()
        if self.thread: self.thread.join(timeout=3)
        if self.path and self.inode:
            try:
                if self.path.lstat().st_ino==self.inode:
                    self.path.unlink()
            except OSError:
                pass
