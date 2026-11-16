"""Small, non-secret, rotating BOOT log independent of the Luma application.

This system-image service deliberately does not read account data or general
journal output. It writes only version markers, signed-updater phases, and
systemd unit states, so the FAT partition remains safe to inspect on Windows.
"""
from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


BOOT_LOG = Path("/boot/firmware/luma-diagnostics.log")
PREVIOUS_LOG = Path("/boot/firmware/luma-diagnostics.previous.log")
LOCK = Path("/run/lock/luma-boot-diagnostics.lock")
UPDATE_STATUS = Path("/opt/luma-releases/.luma-update-status.json")
APP_LINK = Path("/opt/luma")
MAX_LOG_BYTES = 128 * 1024
VERSION = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
SAFE_ATOM = re.compile(r"^[a-z0-9_-]{1,32}$")
SYSTEM_UNITS = {
    "api": "luma-api.service",
    "update": "luma-update.service",
    "update_socket": "luma-update.socket",
}
USER_UNITS = {
    "display": "luma-device.service",
    "voice": "luma-voice.service",
    "kiosk": "luma-kiosk.service",
}


def _atom(value: object, fallback: str = "unknown") -> str:
    return value if isinstance(value, str) and SAFE_ATOM.fullmatch(value) else fallback


def _version(value: object) -> str:
    return value if isinstance(value, str) and VERSION.fullmatch(value) else "unknown"


def read_update_status(path: Path = UPDATE_STATUS) -> dict[str, str]:
    """Never copy a free-form updater error (or other private data) to BOOT."""
    try:
        if path.is_symlink() or path.stat().st_size > 4096:
            return {"state": "unavailable", "phase": "unknown", "target": "unknown"}
        row = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(row, dict):
            raise ValueError("invalid status")
        return {
            "state": _atom(row.get("state")),
            "phase": _atom(row.get("phase")),
            "target": _version(row.get("target_version")),
        }
    except (OSError, ValueError, TypeError):
        return {"state": "unavailable", "phase": "unknown", "target": "unknown"}


def active_version(link: Path = APP_LINK) -> str:
    try:
        return _version(link.resolve(strict=True).name)
    except (OSError, RuntimeError):
        return "unknown"


def _unit_status(unit: str, *, user: bool) -> dict[str, str]:
    command = ["/usr/bin/systemctl"]
    if user:
        command += ["--machine=luma@.host", "--user"]
    command += ["show", unit, "--property=ActiveState,Result,ExecMainStatus,NRestarts", "--no-pager"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=3, check=False)
        if result.returncode:
            raise OSError("systemctl unavailable")
        fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        count = fields.get("NRestarts", "0")
        exit_status = fields.get("ExecMainStatus", "0")
        return {
            "active": _atom(fields.get("ActiveState")),
            "result": _atom(fields.get("Result")),
            "exit": exit_status if exit_status.isdecimal() and len(exit_status) <= 5 else "unknown",
            "restarts": count if count.isdecimal() and len(count) <= 7 else "unknown",
        }
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {"active": "unavailable", "result": "unknown", "exit": "unknown", "restarts": "unknown"}


def snapshot() -> dict[str, object]:
    units = {key: _unit_status(unit, user=False) for key, unit in SYSTEM_UNITS.items()}
    units.update({key: _unit_status(unit, user=True) for key, unit in USER_UNITS.items()})
    return {
        "active_version": active_version(),
        "update": read_update_status(),
        "units": units,
    }


def append_event(event: str, state: dict[str, object], *,
                 path: Path = BOOT_LOG, previous: Path = PREVIOUS_LOG,
                 lock_path: Path = LOCK, boot_id: str = "unknown") -> None:
    """One fsynced JSON line; retain at most two 128 KiB files on the FAT BOOT volume."""
    if event not in {"boot", "status_change", "monitor_restart"}:
        raise ValueError("unknown diagnostic event")
    if path.parent.is_symlink() or not path.parent.is_dir() or previous.parent != path.parent:
        raise OSError("BOOT log directory unavailable")
    row = {
        "at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "boot_id": boot_id if re.fullmatch(r"[0-9a-f-]{36}", boot_id) else "unknown",
        "event": event,
        **state,
    }
    line = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    if len(line) > 2048:
        raise ValueError("diagnostic record too large")
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.is_symlink() or previous.is_symlink():
            raise OSError("BOOT log link refused")
        if path.exists() and path.stat().st_size + len(line) > MAX_LOG_BYTES:
            os.replace(path, previous)
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o644)
        try:
            with os.fdopen(descriptor, "ab", closefd=False) as stream:
                stream.write(line)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(descriptor)


def main() -> int:
    try:
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    except OSError:
        boot_id = "unknown"
    first = True
    last: dict[str, object] | None = None
    failed_log = False
    while True:
        current = snapshot()
        if first or current != last:
            try:
                append_event("boot" if first else "status_change", current, boot_id=boot_id)
                failed_log = False
                last = current
            except (OSError, ValueError) as error:
                if not failed_log:
                    print(f"Luma BOOT diagnostics unavailable: {type(error).__name__}", file=sys.stderr)
                failed_log = True
        first = False
        time.sleep(2 if current["update"]["state"] == "installing" else 20)


if __name__ == "__main__":
    raise SystemExit(main())
