"""Constrained portable-backup operations on pre-mounted removable USB media.

Callers select an opaque volume ID returned by a fresh inventory. They never
submit a filesystem path or filename. Inventory is supplied by the privileged
USB broker; this module additionally refuses symlinked/non-directory roots,
system disks, unsafe backup entries and oversized payloads.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys

from .backup_envelope import MAX_ARCHIVE_BYTES, validate_archive_envelope


BACKUP_DIR = "Luma Backups"
FILE_PREFIX = "luma-settings-"
FILE_SUFFIX = ".lumabackup"
MAX_BACKUPS_PER_VOLUME = 32


class MediaError(ValueError):
    """Safe error for removable-media availability and I/O failures."""


@dataclass(frozen=True, slots=True)
class RemovableVolume:
    id: str
    label: str
    mount_root: Path
    device_node: str
    system_disk: bool = False
    removable_usb: bool = True
    writable: bool = True
    filesystem_device: tuple[int, int] | None = None
    require_mountpoint: bool = True


def _identifier(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{32}", value) is not None


def _backup_name(value):
    return isinstance(value, str) and re.fullmatch(r"luma-settings-\d{8}T\d{6}Z-[a-f0-9]{12}\.lumabackup", value) is not None


def _name_id(name):
    return hashlib.sha256(name.encode("ascii")).hexdigest()[:32]


class BackupMedia:
    """Safe file operations over an injected, freshly checked USB inventory."""
    def __init__(self, enumerate_volumes, *, power_off=None, now=None):
        self.enumerate_volumes = enumerate_volumes
        self.power_off = power_off or self._power_off
        self.now = now or (lambda: datetime.now(UTC))

    @staticmethod
    def _power_off(device_node):
        if not isinstance(device_node, str) or not re.fullmatch(r"/dev/[A-Za-z0-9._/-]{1,80}", device_node):
            raise MediaError("That removable drive could not be safely ejected.")
        try:
            result = subprocess.run(["udisksctl", "power-off", "--block-device", device_node],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, timeout=12, check=False,
                                    env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"})
        except (OSError, subprocess.TimeoutExpired):
            raise MediaError("The backup is saved, but safe eject was unavailable. Use the system eject control.") from None
        if result.returncode:
            raise MediaError("The backup is saved, but the drive did not confirm safe eject. Use the system eject control.")

    def _volumes(self):
        try:
            rows = list(self.enumerate_volumes())
        except Exception:
            raise MediaError("Could not check removable drives.") from None
        seen = set()
        for row in rows:
            if not isinstance(row, RemovableVolume) or not _identifier(row.id) or row.id in seen:
                raise MediaError("Removable-drive inventory needs attention.")
            seen.add(row.id)
        return rows

    def _volume(self, identifier):
        if not _identifier(identifier):
            raise MediaError("Choose a drive from the current removable-drive list.")
        rows = self._volumes()
        row = next((item for item in rows if item.id == identifier), None)
        if (row is None or row.system_disk or not row.removable_usb or not row.writable
                or not isinstance(row.label, str) or not 1 <= len(row.label) <= 80
                or any(ord(char) < 32 or ord(char) == 127 for char in row.label)):
            raise MediaError("That USB drive is unavailable, protected or read-only.")
        try:
            root = Path(row.mount_root)
            info = root.lstat()
            resolved = root.resolve(strict=True)
            if (stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or resolved != root.absolute()
                    or row.require_mountpoint and not os.path.ismount(resolved)):
                raise OSError()
            # The actual mounted filesystem, not the underlying directory, must
            # be openable as a directory. The privileged inventory also ties
            # its major:minor back to the verified USB sysfs identity.
            descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
            root_stat = os.fstat(descriptor)
            if sys.platform == "linux":
                actual_device = (os.major(root_stat.st_dev), os.minor(root_stat.st_dev))
                device_mismatch = row.filesystem_device is None or actual_device != row.filesystem_device
            else:
                # The broker itself is Linux-only. This non-Linux branch exists
                # solely so the pure, injected file-operation tests run on Windows.
                device_mismatch = row.require_mountpoint or row.filesystem_device is not None
            if not stat.S_ISDIR(root_stat.st_mode) or device_mismatch:
                os.close(descriptor)
                raise OSError()
            return row, descriptor
        except (OSError, RuntimeError, TypeError):
            raise MediaError("The selected USB drive changed. Scan drives again.") from None

    def list(self):
        result = []
        for row in self._volumes():
            if row.system_disk or not row.removable_usb or not row.writable:
                continue
            try:
                selected, root_fd = self._volume(row.id)
                try:
                    result.append({"id": selected.id, "label": selected.label,
                                   "backups": self._backups(root_fd)})
                finally:
                    os.close(root_fd)
            except MediaError:
                continue
        return result

    @staticmethod
    def _directory(root_fd, create=False):
        try:
            if create:
                try:
                    os.mkdir(BACKUP_DIR, mode=0o700, dir_fd=root_fd)
                except FileExistsError:
                    pass
            descriptor = os.open(BACKUP_DIR, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
            if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                os.close(descriptor)
                raise OSError()
            return descriptor
        except OSError:
            raise MediaError("The backup folder on this USB drive is not safe to use.") from None

    @staticmethod
    def _backups(root_fd):
        try:
            directory_fd = BackupMedia._directory(root_fd)
        except MediaError:
            try:
                os.stat(BACKUP_DIR, dir_fd=root_fd, follow_symlinks=False)
            except FileNotFoundError:
                return []
            raise
        try:
            entries = []
            for name in os.listdir(directory_fd):
                if not _backup_name(name):
                    continue
                try:
                    metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode) or metadata.st_size > MAX_ARCHIVE_BYTES:
                        continue
                    entries.append({"id": _name_id(name), "created_at": datetime.strptime(
                        name[len(FILE_PREFIX):len(FILE_PREFIX) + 16], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC).isoformat()})
                except (OSError, ValueError):
                    continue
            entries.sort(key=lambda item: item["created_at"], reverse=True)
            return entries[:MAX_BACKUPS_PER_VOLUME]
        except OSError:
            return []
        finally:
            os.close(directory_fd)

    def write(self, volume_id, data):
        if not validate_archive_envelope(data):
            raise MediaError("Choose a supported, encrypted Luma settings backup.")
        row, root_fd = self._volume(volume_id)
        directory_fd = None
        try:
            directory_fd = self._directory(root_fd, create=True)
            if len(self._backups(root_fd)) >= MAX_BACKUPS_PER_VOLUME:
                raise MediaError("This USB drive already has 32 Luma backups. Move an older backup off the drive first.")
            created = self.now().astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
            token = secrets.token_hex(6)
            target_name = f"{FILE_PREFIX}{created}-{token}{FILE_SUFFIX}"
            temporary = f".luma-pending-{secrets.token_hex(16)}.tmp"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
            with os.fdopen(descriptor, "wb", closefd=True) as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            verify_info = os.stat(temporary, dir_fd=directory_fd, follow_symlinks=False)
            if not stat.S_ISREG(verify_info.st_mode) or verify_info.st_size != len(data):
                raise OSError()
            descriptor = os.open(temporary, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
            with os.fdopen(descriptor, "rb") as source:
                if source.read(MAX_ARCHIVE_BYTES + 1) != bytes(data):
                    raise OSError()
            # A hard-link publish is atomic and fails if the final name exists;
            # the previous last-good export is never replaced.
            os.link(temporary, target_name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd, follow_symlinks=False)
            os.unlink(temporary, dir_fd=directory_fd)
            os.fsync(directory_fd)
            return {"id": _name_id(target_name), "created_at": self.now().astimezone(UTC).isoformat(), "verified": True}
        except MediaError:
            raise
        except (OSError, ValueError):
            raise MediaError("The USB backup could not be written and verified. The previous backup was kept.") from None
        finally:
            if directory_fd is not None:
                try:
                    os.close(directory_fd)
                except OSError:
                    pass
            os.close(root_fd)

    def read(self, volume_id, backup_id):
        if not _identifier(backup_id):
            raise MediaError("Choose a backup from the current USB-drive list.")
        _, root_fd = self._volume(volume_id)
        directory_fd = None
        try:
            directory_fd = self._directory(root_fd)
            matches = [name for name in os.listdir(directory_fd) if _backup_name(name) and _name_id(name) == backup_id]
            if len(matches) != 1:
                raise MediaError("That backup is no longer available. Scan the drive again.")
            name = matches[0]
            metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode) or not 1 <= metadata.st_size <= MAX_ARCHIVE_BYTES:
                raise OSError()
            descriptor = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
            with os.fdopen(descriptor, "rb") as source:
                data = source.read(MAX_ARCHIVE_BYTES + 1)
            if len(data) != metadata.st_size or len(data) > MAX_ARCHIVE_BYTES:
                raise OSError()
            return data
        except MediaError:
            raise
        except OSError:
            raise MediaError("That backup file could not be read safely.") from None
        finally:
            if directory_fd is not None:
                os.close(directory_fd)
            os.close(root_fd)

    def eject(self, volume_id):
        row, root_fd = self._volume(volume_id)
        try:
            os.fsync(root_fd)
            self.power_off(row.device_node)
        except MediaError:
            raise
        except OSError:
            raise MediaError("The drive could not be flushed. Leave it connected and try safe eject again.") from None
        finally:
            os.close(root_fd)
        return {"ejected": True}
