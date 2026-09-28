"""Root-owned USB backup broker; only the Luma service UID may use its socket."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
import struct
from contextlib import suppress

from .backup_inventory import LinuxUSBInventory
from .backup_media import BackupMedia, MediaError
from .portable_backup import MAX_ARCHIVE_BYTES


SOCKET = "/run/luma-backup.sock"
MAX_WIRE = MAX_ARCHIVE_BYTES * 2 + 4096


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def validate_request(value):
    if not isinstance(value, dict) or not isinstance(value.get("action"), str):
        raise ValueError("Invalid removable-drive request.")
    action = value["action"]
    allowed = {
        "scan": {"action"}, "list": {"action"},
        "write": {"action", "volume_id", "archive"},
        "read": {"action", "volume_id", "backup_id"},
        "eject": {"action", "volume_id"},
    }
    if action not in allowed or set(value) != allowed[action]:
        raise ValueError("Invalid removable-drive request.")
    for key in ("volume_id", "backup_id"):
        item = value.get(key)
        if key in value and (not isinstance(item, str) or len(item) != 32):
            raise ValueError("Invalid removable-drive selection.")
    if action == "write" and (not isinstance(value["archive"], str)
                               or len(value["archive"]) > ((MAX_ARCHIVE_BYTES + 2) // 3) * 4):
        raise ValueError("Invalid encrypted backup payload.")
    return value


class BackupBroker:
    def __init__(self, inventory=None, media=None):
        self.inventory = inventory or LinuxUSBInventory()
        self.media = media or BackupMedia(self.inventory.current_volumes)

    def execute(self, request):
        value = validate_request(request)
        action = value["action"]
        if action == "scan":
            self.inventory.scan(mount=True)
            return {"volumes": self.media.list()}
        if action == "list":
            return {"volumes": self.media.list()}
        if action == "write":
            try:
                archive = base64.b64decode(value["archive"], validate=True)
            except (ValueError, TypeError):
                raise ValueError("Invalid encrypted backup payload.") from None
            if len(archive) > MAX_ARCHIVE_BYTES:
                raise ValueError("The encrypted backup is too large.")
            return self.media.write(value["volume_id"], archive)
        if action == "read":
            archive = self.media.read(value["volume_id"], value["backup_id"])
            return {"archive": base64.b64encode(archive).decode("ascii")}
        if action == "eject":
            result = self.media.eject(value["volume_id"])
            return result
        raise ValueError("Invalid removable-drive request.")


def _peer_is_luma(writer):
    try:
        import pwd
        peer = writer.get_extra_info("socket").getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        return struct.unpack("3i", peer)[1] == pwd.getpwnam("luma").pw_uid
    except (AttributeError, OSError, KeyError, struct.error):
        return False


async def _serve_listener(listener, broker):
    """Serve one systemd-provided listener; isolated for socket integration tests."""
    lock = asyncio.Lock()

    async def handle(reader, writer):
        result = {"error": "Removable-drive operation failed."}
        try:
            if not _peer_is_luma(writer):
                return
            raw = await asyncio.wait_for(reader.readline(), 10)
            if not raw or len(raw) > MAX_WIRE:
                raise ValueError()
            request = json.loads(raw, object_pairs_hook=_object)
            if lock.locked():
                result = {"error": "Removable-drive operation is busy; try again shortly."}
            else:
                async with lock:
                    result = await asyncio.wait_for(asyncio.to_thread(broker.execute, request), 35)
        except (ValueError, json.JSONDecodeError, asyncio.TimeoutError):
            result = {"error": "Invalid, expired or unavailable removable-drive selection."}
        except Exception:
            # Never return filesystem paths, device metadata, or exception strings.
            result = {"error": "Removable-drive operation failed. Keep the drive connected and rescan."}
        finally:
            if not writer.is_closing():
                with suppress(Exception):
                    writer.write(json.dumps(result, separators=(",", ":")).encode() + b"\n")
                    await writer.drain()
                writer.close()
                with suppress(Exception):
                    await writer.wait_closed()

    server = await asyncio.start_unix_server(handle, sock=listener, limit=MAX_WIRE)
    async with server:
        await server.serve_forever()


async def serve():
    if (os.geteuid() != 0 or os.environ.get("LISTEN_PID") != str(os.getpid())
            or os.environ.get("LISTEN_FDS") != "1"):
        raise RuntimeError("Start through luma-backup.socket")
    listener = socket.socket(fileno=3)
    await _serve_listener(listener, BackupBroker())


async def backup_request(request):
    """Call the root broker. The API caller never handles device paths."""
    validate_request(request)
    if not hasattr(asyncio, "open_unix_connection"):
        raise MediaError("USB recovery is available on the Luma device.")
    writer = None
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(SOCKET, limit=MAX_WIRE), 4)
        payload = json.dumps(request, separators=(",", ":")).encode() + b"\n"
        if len(payload) > MAX_WIRE:
            raise ValueError()
        writer.write(payload)
        await writer.drain()
        raw = await asyncio.wait_for(reader.readline(), 40)
        if not raw or len(raw) > MAX_WIRE:
            raise ValueError()
        result = json.loads(raw, object_pairs_hook=_object)
        if not isinstance(result, dict):
            raise ValueError()
        if "error" in result:
            raise MediaError(result["error"])
        return result
    except MediaError:
        raise
    except (OSError, TimeoutError, ValueError, json.JSONDecodeError, asyncio.IncompleteReadError):
        raise MediaError("USB recovery is unavailable. Check that the drive is connected and rescan.") from None
    finally:
        if writer:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()


def main():
    asyncio.run(serve())
