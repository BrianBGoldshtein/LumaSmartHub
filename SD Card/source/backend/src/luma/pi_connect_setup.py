"""Physical-screen enrollment for a dedicated Raspberry Pi Connect admin shell.

The browser can request only a status check, a one-time owner sign-in, or an
explicit remote-shell on/off.  The broker runs unprivileged as luma-admin and
accepts requests only from the local Luma API user's Unix-socket connection.
Verification links and QR images are held in RAM briefly and are never logged
or persisted by Luma.
"""
from __future__ import annotations

import asyncio
import base64
from contextlib import suppress
import json
import os
from pathlib import Path
import re
import socket
import struct
from time import monotonic

SOCKET = "/run/luma-pi-connect-setup.sock"
CLI = "/usr/bin/rpi-connect"
QR = "/usr/bin/qrencode"
ADMIN = "luma-admin"
ADMIN_HOME = "/home/luma-admin"
SHELL_APPROVAL = Path(ADMIN_HOME) / ".config/luma/remote-shell-approved"
VERIFY_URL = re.compile(r"https://connect\.raspberrypi\.com/verify/[A-Za-z0-9-]{6,80}")
ACTION_SET = {"status", "diagnose", "signin", "shell_on", "shell_off"}
PENDING_SECONDS = 600
MAX_OUTPUT = 65536
START_TIMEOUT = 45
SIGNIN_TIMEOUT = 50
DIAGNOSE_TIMEOUT = 45


def parse_doctor(output: bytes) -> dict[str, bool | None]:
    """Project official CLI diagnostics onto fixed, non-sensitive checks."""
    labels = {
        "api": "Communication with Raspberry Pi Connect API",
        "websocket": "Communication with Raspberry Pi Connect WebSocket server",
        "stun": "Peer-to-peer connection candidate via STUN",
        "turn": "Peer-to-peer connection candidate via TURN",
    }
    checks: dict[str, bool | None] = {key: None for key in labels}
    for line in output.decode("utf-8", "replace").splitlines():
        for key, label in labels.items():
            if label not in line:
                continue
            marker = line.split(label, 1)[0]
            if "✓" in marker:
                checks[key] = True
            elif "✗" in marker:
                checks[key] = False
    return checks


def validate_request(value: object) -> dict[str, str]:
    if (not isinstance(value, dict) or set(value) != {"action"}
            or not isinstance(value["action"], str) or value["action"] not in ACTION_SET):
        raise ValueError("Invalid Raspberry Pi Connect request")
    return value


def _environment() -> dict[str, str]:
    uid = os.getuid()
    return {
        "HOME": ADMIN_HOME,
        "USER": ADMIN,
        "LOGNAME": ADMIN,
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "LANG": "C.UTF-8",
        "XDG_RUNTIME_DIR": f"/run/user/{uid}",
        "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{uid}/bus",
    }


async def run_command(*args: str, input_data: bytes | None = None, timeout: float = 15) -> tuple[int, bytes]:
    """Run a fixed executable with a minimal admin-user environment."""
    command = args[0]
    process = await asyncio.create_subprocess_exec(
        command, *args[1:], stdin=asyncio.subprocess.PIPE if input_data is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        limit=MAX_OUTPUT, env=_environment())
    try:
        async with asyncio.timeout(timeout):
            output, _ = await process.communicate(input_data)
        if len(output) > MAX_OUTPUT:
            raise ValueError("Pi Connect response was too large")
        return process.returncode or 0, output
    finally:
        if process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
            await process.wait()


async def qr_data(url: str) -> str | None:
    """Build a local QR image; never send the one-time link to a QR website."""
    if not Path(QR).is_file():
        return None
    try:
        code, image = await run_command(QR, "-t", "PNG", "-o", "-", "-s", "6", "-m", "2",
                                        input_data=url.encode("ascii"), timeout=5)
    except (OSError, TimeoutError, ValueError):
        return None
    if code or len(image) > 128 * 1024 or not image.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    return "data:image/png;base64," + base64.b64encode(image).decode("ascii")


def parse_status(output: bytes) -> dict[str, object]:
    """Return only the two access facts needed by the local setup page."""
    text = output.decode("utf-8", "replace")
    signed = re.search(r"(?im)^\s*Signed in:\s*(yes|no)\s*$", text)
    shell = re.search(r"(?im)^\s*Remote shell:\s*(allowed|disabled|disallowed|not allowed)\b", text)
    if not signed:
        if "not running" in text.casefold():
            return {"available": True, "state": "off", "signed_in": False, "remote_shell": False}
        return {"available": True, "state": "unavailable", "signed_in": False, "remote_shell": False}
    signed_in = signed.group(1).casefold() == "yes"
    shell_allowed = bool(shell and shell.group(1).casefold() == "allowed")
    return {
        "available": True,
        "state": "remote_shell_enabled" if signed_in and shell_allowed else "signed_in" if signed_in else "not_signed_in",
        "signed_in": signed_in,
        "remote_shell": shell_allowed,
    }


class PiConnectSetup:
    def __init__(self, runner=run_command, qr=qr_data, clock=monotonic, installed=None,
                 shell_approval: Path = SHELL_APPROVAL):
        self.run = runner
        self.qr = qr
        self.clock = clock
        self.installed = installed or (lambda: Path(CLI).is_file())
        self.shell_approval = shell_approval
        self.verification_url: str | None = None
        self.qr_image: str | None = None
        self.pending_until = 0.0

    async def _command(self, *args: str) -> bytes:
        stage = " ".join(args)
        timeout = START_TIMEOUT if args == ("on",) else SIGNIN_TIMEOUT if args == ("signin",) else 20
        try:
            code, output = await self.run(CLI, *args, timeout=timeout)
        except TimeoutError:
            if stage == "signin":
                raise ValueError("Pi Connect timed out requesting sign-in. Check its network diagnostics or try another permitted network.") from None
            raise ValueError("Pi Connect took too long to start. Refresh status and try again.") from None
        except OSError:
            raise ValueError("Pi Connect could not launch on this device. Check its status and diagnostics.") from None
        if code:
            if stage == "on":
                raise ValueError("Pi Connect could not start its admin session. Refresh status and try again.")
            if stage == "signin":
                raise ValueError("Pi Connect could not request sign-in. Check its service and Internet access.")
            raise ValueError("Pi Connect could not change remote-shell access. Refresh status and try again.")
        return output

    def _clear_shell_approval(self) -> None:
        self.shell_approval.unlink(missing_ok=True)

    def _approve_shell(self) -> None:
        self.shell_approval.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.shell_approval.write_text("owner enabled remote shell\n", encoding="ascii")
        self.shell_approval.chmod(0o600)

    async def _status(self) -> dict[str, object]:
        if not self.installed():
            return {"available": False, "state": "not_installed", "signed_in": False,
                    "remote_shell": False}
        try:
            code, output = await self.run(CLI, "status", timeout=12)
        except (OSError, TimeoutError):
            return {"available": True, "state": "unavailable", "signed_in": False,
                    "remote_shell": False}
        if code and not output:
            output = b"Raspberry Pi Connect is not running"
        result = parse_status(output)
        if result["signed_in"] and result["remote_shell"] and not self.shell_approval.is_file():
            # Connect does not permit changing access before sign-in. Its
            # default shell permission is removed as soon as approval is
            # observed; only the separate local owner button persists it.
            await self._command("shell", "off")
            _, output = await self.run(CLI, "status", timeout=12)
            result = parse_status(output)
        if result["signed_in"]:
            self.verification_url = self.qr_image = None
        elif self.verification_url and self.clock() <= self.pending_until:
            result.update(state="awaiting_approval", verification_url=self.verification_url,
                          qr=self.qr_image)
        else:
            self.verification_url = self.qr_image = None
        return result

    async def execute(self, request: object) -> dict[str, object]:
        action = validate_request(request)["action"]
        if action == "status":
            return await self._status()
        if action == "diagnose":
            if not self.installed():
                return {"available": False, "checks": parse_doctor(b"")}
            try:
                _code, output = await self.run(CLI, "doctor", timeout=DIAGNOSE_TIMEOUT)
            except (OSError, TimeoutError):
                raise ValueError("Pi Connect diagnostics could not finish. Check its service or network.") from None
            return {"available": True, "checks": parse_doctor(output)}
        if action == "signin":
            if not self.installed():
                return await self._status()
            current = await self._status()
            if current["signed_in"]:
                return current
            self._clear_shell_approval()
            # The official client can take almost the old 20-second command
            # limit merely to start. Don't restart an already-running service.
            if current["state"] in {"off", "unavailable"}:
                await self._command("on")
            # Connect rejects shell/vnc changes until account approval. The
            # image uses shell-only Connect Lite, so no VNC endpoint exists.
            output = await self._command("signin")
            match = VERIFY_URL.search(output.decode("utf-8", "replace"))
            status = await self._status()
            if status["signed_in"]:
                return status
            if not match:
                raise ValueError("No verification link was returned. Refresh Pi Connect status and retry.")
            self.verification_url = match.group(0)
            self.qr_image = await self.qr(self.verification_url)
            self.pending_until = self.clock() + PENDING_SECONDS
            return {**status, "state": "awaiting_approval", "verification_url": self.verification_url,
                    "qr": self.qr_image}
        if action == "shell_on":
            current = await self._status()
            if not current["available"]:
                return current
            if not current["signed_in"]:
                raise ValueError("Approve this Pi in your Raspberry Pi Connect account first.")
            await self._command("shell", "on")
            try:
                self._approve_shell()
            except OSError:
                await self._command("shell", "off")
                raise ValueError("Pi Connect could not preserve the shell approval. Try again.") from None
            current = await self._status()
            if not current["remote_shell"]:
                raise ValueError("Pi Connect did not confirm that remote shell is enabled. Refresh status and retry.")
            return current
        current = await self._status()
        if not current["available"] or not current["signed_in"]:
            return current
        self._clear_shell_approval()
        await self._command("shell", "off")
        return await self._status()


async def pi_connect_request(request: object) -> dict[str, object]:
    validate_request(request)
    writer = None
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(SOCKET, limit=MAX_OUTPUT), 3)
        writer.write(json.dumps(request, separators=(",", ":")).encode("utf-8") + b"\n")
        await writer.drain()
        response = json.loads(await asyncio.wait_for(reader.readline(), 130))
        if not isinstance(response, dict):
            raise ValueError("Invalid Pi Connect response")
        if "error" in response:
            raise ValueError(response["error"])
        return response
    except ValueError:
        raise
    except (OSError, TimeoutError, json.JSONDecodeError, NotImplementedError):
        raise ValueError("Pi Connect setup is available on the updated Luma image; apply that image first.") from None
    finally:
        if writer:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()


async def serve(*, listener: socket.socket | None = None, owner_uid: int | None = None,
                manager: PiConnectSetup | None = None) -> None:
    import pwd
    if listener is None:
        if os.environ.get("LISTEN_PID") != str(os.getpid()) or os.environ.get("LISTEN_FDS") != "1":
            raise RuntimeError("Start Pi Connect setup through its systemd socket")
        listener = socket.socket(fileno=3)
    if owner_uid is None:
        owner_uid = pwd.getpwnam("luma").pw_uid
    manager = manager or PiConnectSetup()
    lock = asyncio.Lock()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        response: dict[str, object] | None = None
        try:
            peer = writer.get_extra_info("socket").getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            if struct.unpack("3i", peer)[1] != owner_uid:
                return
            raw = await asyncio.wait_for(reader.readline(), 3)
            if len(raw) > 256:
                raise ValueError("Request too large")
            request = validate_request(json.loads(raw))
            if lock.locked():
                response = {"error": "Pi Connect setup is busy; try again shortly."}
            else:
                async with lock:
                    response = await asyncio.wait_for(manager.execute(request), 125)
        except ValueError as error:
            response = {"error": str(error)}
        except Exception:
            response = {"error": "Pi Connect setup is unavailable. Check the updated image and device status."}
        finally:
            if response is not None:
                with suppress(Exception):
                    writer.write(json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n")
                    await writer.drain()
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()

    server = await asyncio.start_unix_server(handle, sock=listener, limit=MAX_OUTPUT)
    async with server:
        await server.serve_forever()


def main() -> None:
    asyncio.run(serve())
