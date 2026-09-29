"""Root-owned socket broker for verified, atomic Luma application updates."""
from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path
import socket
import struct
from contextlib import suppress

from .update_agent import MAX_BUNDLE_BYTES, PUBLIC_KEY, UpdateError, apply_bundle, staged_bundle, verify_bundle


SOCKET = "/run/luma-update.sock"
MAX_WIRE = ((MAX_BUNDLE_BYTES + 2) // 3) * 4 + 4096


def validate_request(value):
    if not isinstance(value, dict) or value.get("action") not in {"status", "install"}:
        raise ValueError("Invalid Luma update request.")
    action = value["action"]
    if set(value) != ({"action"} if action == "status" else {"action", "bundle"}):
        raise ValueError("Invalid Luma update request.")
    if action == "install" and (not isinstance(value["bundle"], str)
                                  or len(value["bundle"]) > ((MAX_BUNDLE_BYTES + 2) // 3) * 4):
        raise ValueError("Invalid Luma update bundle.")
    return value


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def _peer_is_luma(writer):
    try:
        import pwd
        peer = writer.get_extra_info("socket").getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        return struct.unpack("3i", peer)[1] == pwd.getpwnam("luma").pw_uid
    except (AttributeError, OSError, KeyError, struct.error):
        return False


class UpdateBroker:
    """Verify requests as root, then install outside the API process lifetime."""

    def __init__(self, *, installer=apply_bundle, public_key_path: Path = PUBLIC_KEY):
        self.installer = installer
        self.public_key_path = public_key_path
        self.state = "idle"
        self.version: str | None = None
        self.message = ""
        self._lock = asyncio.Lock()

    def status(self):
        return {"state": self.state, "target_version": self.version, "message": self.message}

    async def accept(self, value):
        value = validate_request(value)
        if value["action"] == "status":
            return self.status(), None
        if self._lock.locked() or self.state == "installing":
            return {"error": "A Luma update is already being installed."}, None
        try:
            bundle = base64.b64decode(value["bundle"], validate=True)
        except (ValueError, TypeError):
            return {"error": "The Luma update bundle is invalid."}, None
        if not bundle or len(bundle) > MAX_BUNDLE_BYTES:
            return {"error": "The Luma update bundle is too large."}, None
        async with self._lock:
            if self.state == "installing":
                return {"error": "A Luma update is already being installed."}, None
            try:
                verified = await asyncio.to_thread(self._verify, bundle)
            except UpdateError as error:
                return {"error": str(error)}, None
            self.state = "installing"
            self.version = verified["version"]
            self.message = "Luma is installing the verified update."
        return {"accepted": True, "version": self.version}, bundle

    def _verify(self, bundle):
        with staged_bundle(bundle, prefix="luma-update-verify-") as bundle_path:
            return verify_bundle(bundle_path, self.public_key_path)

    async def install(self, bundle):
        try:
            with staged_bundle(bundle, prefix="luma-update-") as bundle_path:
                await asyncio.to_thread(self.installer, bundle_path,
                                        public_key_path=self.public_key_path)
            self.state = "installed"
            self.message = "The new release passed its health check."
        except UpdateError as error:
            self.state = "failed"
            self.message = str(error)
        except Exception:
            self.state = "failed"
            self.message = "The update failed; Luma's previous release remains active."


async def _serve_listener(listener, broker):
    async def handle(reader, writer):
        task_bundle = None
        result = {"error": "Luma update operation failed."}
        try:
            if not _peer_is_luma(writer):
                return
            raw = await asyncio.wait_for(reader.readline(), 60)
            if not raw or len(raw) > MAX_WIRE:
                raise ValueError()
            request = json.loads(raw, object_pairs_hook=_no_duplicates)
            result, task_bundle = await broker.accept(request)
        except (ValueError, json.JSONDecodeError, asyncio.TimeoutError):
            result = {"error": "Invalid or expired Luma update request."}
        except Exception:
            result = {"error": "Luma update service is unavailable. Use Pi Connect for recovery."}
        finally:
            if not writer.is_closing():
                with suppress(Exception):
                    writer.write(json.dumps(result, separators=(",", ":")).encode() + b"\n")
                    await writer.drain()
                writer.close()
                with suppress(Exception):
                    await writer.wait_closed()
        if task_bundle is not None:
            asyncio.create_task(broker.install(task_bundle))

    server = await asyncio.start_unix_server(handle, sock=listener, limit=MAX_WIRE)
    async with server:
        await server.serve_forever()


async def serve():
    if (os.geteuid() != 0 or os.environ.get("LISTEN_PID") != str(os.getpid())
            or os.environ.get("LISTEN_FDS") != "1"):
        raise RuntimeError("Start through luma-update.socket")
    listener = socket.socket(fileno=3)
    await _serve_listener(listener, UpdateBroker())


async def update_request(request):
    """Call the root broker; only a verified Luma bundle can change the app."""
    validate_request(request)
    writer = None
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(SOCKET, limit=MAX_WIRE), 4)
        payload = json.dumps(request, separators=(",", ":")).encode() + b"\n"
        if len(payload) > MAX_WIRE:
            raise ValueError()
        writer.write(payload)
        await writer.drain()
        raw = await asyncio.wait_for(reader.readline(), 65)
        if not raw or len(raw) > 4096:
            raise ValueError()
        result = json.loads(raw, object_pairs_hook=_no_duplicates)
        if not isinstance(result, dict):
            raise ValueError()
        if "error" in result:
            raise UpdateError(result["error"])
        return result
    except UpdateError:
        raise
    except (OSError, TimeoutError, ValueError, json.JSONDecodeError, asyncio.IncompleteReadError):
        raise UpdateError("Luma update service is unavailable. Use Pi Connect for recovery.") from None
    finally:
        if writer:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()


def main():
    asyncio.run(serve())
