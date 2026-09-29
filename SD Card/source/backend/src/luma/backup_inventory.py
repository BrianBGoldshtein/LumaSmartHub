"""Root-side removable USB inventory for portable settings backups.

The kiosk API never supplies paths.  A volume ID is minted only by ``scan``;
each operation re-enumerates block devices and matches the ID against the
same USB device, filesystem UUID, and major/minor tuple before use.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import subprocess
from time import monotonic

from .backup_media import RemovableVolume


_LSBLK = ["lsblk", "--json", "--paths", "--output",
          "NAME,PATH,TYPE,RM,TRAN,FSTYPE,LABEL,UUID,MAJ:MIN,PKNAME,MOUNTPOINTS"]
_SAFE_FILESYSTEMS = {"vfat", "fat", "fat32", "exfat", "ext2", "ext3", "ext4", "ntfs", "ntfs3"}


def _unescape_mount(value: str) -> str:
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), value)


def _mount_devices(mountinfo: str) -> set[tuple[str, str]]:
    result = set()
    for line in mountinfo.splitlines():
        fields = line.split()
        if len(fields) < 7:
            continue
        target = _unescape_mount(fields[4])
        if target in {"/", "/boot", "/boot/firmware"}:
            major, sep, minor = fields[2].partition(":")
            if sep and major.isdigit() and minor.isdigit():
                result.add((major, minor))
    return result


def _read_only_devices(mountinfo: str) -> set[tuple[str, str]]:
    result = set()
    for line in mountinfo.splitlines():
        fields = line.split()
        if len(fields) < 7 or "ro" not in fields[5].split(","):
            continue
        major, sep, minor = fields[2].partition(":")
        if sep and major.isdigit() and minor.isdigit():
            result.add((major, minor))
    return result


class LinuxUSBInventory:
    """Enumerate mountable USB filesystems without accepting client paths."""

    def __init__(self, *, runner=subprocess.run, sys_dev_block="/sys/dev/block",
                 mountinfo="/proc/self/mountinfo", clock=monotonic):
        self.runner = runner
        self.sys_dev_block = Path(sys_dev_block)
        self.mountinfo = Path(mountinfo)
        self._known: dict[str, tuple[str, str, str, str]] = {}
        self.clock = clock
        self._scanned_at = 0.0

    def _run(self, args, *, timeout=6):
        try:
            return self.runner(args, stdin=subprocess.DEVNULL, capture_output=True,
                               text=True, timeout=timeout, check=True,
                               env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"}).stdout
        except (OSError, subprocess.SubprocessError):
            raise ValueError("Removable-drive discovery is unavailable.") from None

    def _rows(self):
        try:
            raw = json.loads(self._run(_LSBLK))
            roots = raw["blockdevices"]
            if not isinstance(roots, list):
                raise ValueError()
            rows = {}

            def visit(item, parent=None):
                if not isinstance(item, dict):
                    return
                name = item.get("name")
                path = item.get("path")
                if isinstance(name, str) and isinstance(path, str) and path.startswith("/dev/"):
                    item = dict(item)
                    if parent and not item.get("pkname"):
                        item["pkname"] = parent
                    rows[name.removeprefix("/dev/")] = item
                    parent = name.removeprefix("/dev/")
                children = item.get("children") or []
                if isinstance(children, list):
                    for child in children:
                        visit(child, parent)

            for root in roots:
                visit(root)
            return rows
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise ValueError("Removable-drive inventory returned an invalid result.") from None

    @staticmethod
    def _disk_ancestor(row, rows):
        current = row
        visited = set()
        while current:
            name = current.get("name", "").removeprefix("/dev/")
            if name in visited:
                return None
            visited.add(name)
            if current.get("type") == "disk":
                return current
            parent = current.get("pkname")
            current = rows.get(str(parent).removeprefix("/dev/")) if parent else None
        return None

    def _physical_usb(self, row, rows):
        disk = self._disk_ancestor(row, rows)
        if not disk:
            return None
        tran = str(disk.get("tran") or "").lower()
        try:
            sysfs = (self.sys_dev_block / str(disk["maj:min"])).resolve(strict=True)
            sysfs_usb = any(part == "usb" or re.fullmatch(r"usb\d+", part) for part in sysfs.parts)
        except (KeyError, OSError):
            sysfs_usb = False
        # lsblk's RM flag is a device-reported removable bit, not a reliable
        # indication that storage is physically connected over USB. Transport
        # plus USB sysfs ancestry provide the stronger identity check.
        return disk if tran == "usb" and sysfs_usb else None

    def _candidate_rows(self):
        rows = self._rows()
        try:
            mountinfo = self.mountinfo.read_text(encoding="utf-8")
            protected = _mount_devices(mountinfo)
            readonly = _read_only_devices(mountinfo)
        except OSError:
            raise ValueError("The system-drive protection check is unavailable.") from None
        protected_disks = set()
        for row in rows.values():
            major_minor = row.get("maj:min")
            if isinstance(major_minor, str) and tuple(major_minor.split(":", 1)) in protected:
                disk = self._disk_ancestor(row, rows)
                if disk and isinstance(disk.get("path"), str):
                    protected_disks.add(disk["path"])
        candidates = []
        for row in rows.values():
            if row.get("type") != "part" or str(row.get("fstype") or "").lower() not in _SAFE_FILESYSTEMS:
                continue
            device = row.get("path")
            uuid = row.get("uuid")
            major_minor = row.get("maj:min")
            if not (isinstance(device, str) and re.fullmatch(r"/dev/[A-Za-z0-9._/-]{1,80}", device)
                    and isinstance(uuid, str) and 1 <= len(uuid) <= 128
                    and isinstance(major_minor, str) and re.fullmatch(r"\d+:\d+", major_minor)):
                continue
            physical = self._physical_usb(row, rows)
            if not physical or physical["path"] in protected_disks:
                continue
            protected_ancestry = False
            current = row
            while current:
                mm = str(current.get("maj:min", ""))
                if ":" in mm and tuple(mm.split(":", 1)) in protected:
                    protected_ancestry = True
                    break
                parent = current.get("pkname")
                current = rows.get(str(parent).removeprefix("/dev/")) if parent else None
            if protected_ancestry:
                continue
            candidates.append((row, physical, uuid, major_minor, tuple(major_minor.split(":")) not in readonly))
        return candidates

    @staticmethod
    def _label(row):
        raw = row.get("label")
        if not isinstance(raw, str):
            return "USB drive"
        clean = "".join(c for c in raw if ord(c) >= 32 and ord(c) != 127).strip()
        return clean[:80] or "USB drive"

    def scan(self, *, mount=False):
        """Refresh the short-lived IDs. Mount only eligible USB filesystems."""
        candidates = self._candidate_rows()
        if mount:
            for row, _, _, _, _ in candidates[:16]:
                mounts = row.get("mountpoints")
                if not any(isinstance(item, str) and item for item in (mounts or [])):
                    self._run(["udisksctl", "mount", "--block-device", row["path"], "--no-user-interaction"], timeout=25)
            candidates = self._candidate_rows()
        known = {}
        volumes = []
        for row, physical, uuid, major_minor, writable in candidates[:16]:
            mounts = row.get("mountpoints") or []
            mount_root = next((item for item in mounts if isinstance(item, str) and item.startswith("/")), None)
            if not mount_root:
                continue
            identity = (row["path"], uuid, major_minor, physical["path"])
            old_id = next((key for key, value in self._known.items() if value == identity), None)
            volume_id = old_id or secrets.token_hex(16)
            known[volume_id] = identity
            try:
                filesystem_device = tuple(int(part) for part in major_minor.split(":"))
            except (TypeError, ValueError):
                continue
            volumes.append(RemovableVolume(
                id=volume_id, label=self._label(row), mount_root=Path(mount_root),
                device_node=physical["path"], system_disk=False, removable_usb=True,
                writable=writable and os.access(mount_root, os.W_OK), filesystem_device=filesystem_device,
                require_mountpoint=True,
            ))
        self._known = known
        self._scanned_at = self.clock()
        return volumes

    def current_volumes(self):
        """Revalidate every ID from the last UI scan against live lsblk state."""
        if not self._known or self.clock() - self._scanned_at > 300:
            self._known = {}
            return []
        previously_known = self._known
        current = []
        for row, physical, uuid, major_minor, writable in self._candidate_rows():
            identity = (row["path"], uuid, major_minor, physical["path"])
            volume_id = next((key for key, value in previously_known.items() if value == identity), None)
            if not volume_id:
                continue
            mounts = row.get("mountpoints") or []
            mount_root = next((item for item in mounts if isinstance(item, str) and item.startswith("/")), None)
            if not mount_root:
                continue
            current.append(RemovableVolume(
                id=volume_id, label=self._label(row), mount_root=Path(mount_root),
                device_node=physical["path"], system_disk=False, removable_usb=True,
                writable=writable and os.access(mount_root, os.W_OK),
                filesystem_device=tuple(int(part) for part in major_minor.split(":")),
                require_mountpoint=True,
            ))
        # A volume ID is a short-lived capability, not a reusable filesystem path.
        self._known = {volume.id: previously_known[volume.id] for volume in current}
        return current
