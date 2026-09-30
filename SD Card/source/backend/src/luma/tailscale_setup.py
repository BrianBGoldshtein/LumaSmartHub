"""Local touch enrollment, never a generic privileged command executor.

No account password, auth key, routes, hostname, URL or shell input is accepted.
The dedicated daemon starts only after a touchscreen request. Its identity lives
outside Luma backups; QR enrollment output is held in RAM for at most 5 minutes.
"""
from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import os
import re
import socket
import struct
from time import monotonic

SOCKET = "/run/luma-tailscale-setup.sock"
CLI = ("/opt/luma/tailscale/tailscale", "--socket=/run/luma-tailscale/tailscaled.sock")
SYSTEMCTL = "/usr/bin/systemctl"
DAEMON = "luma-tailscaled.service"
GATEWAY = "luma-shortcut-gateway.service"
AUTH_URL = re.compile(r"https://login\.tailscale\.com/a/[a-zA-Z0-9_-]{6,128}\Z")
DNS_NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.[a-z0-9-]{1,63}\.ts\.net\Z")
PNG_DATA = re.compile(r"data:image/png;base64,[A-Za-z0-9+/=]{1,32000}\Z")
ACTIONS = {"status", "connect", "enable", "disconnect"}


def validate_request(value):
    if not isinstance(value, dict) or set(value) != {"action"} or not isinstance(value["action"], str) or value["action"] not in ACTIONS:
        raise ValueError("Invalid private connection request")
    return value


async def run_command(*args, timeout=12):
    """Fixed argv only; no shell, stdin, environment proxy, or output logging."""
    process = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, limit=131072,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "HOME": "/", "LANG": "C.UTF-8"})
    try:
        async def collect():
            output = bytearray()
            while chunk := await process.stdout.read(8192):
                output.extend(chunk)
                if len(output) > 131072:
                    raise ValueError("Private connection response too large")
            await process.wait()
            return process.returncode, output.decode("utf-8")
        return await asyncio.wait_for(collect(), timeout)
    finally:
        if process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
            await process.wait()


def json_objects(output):
    """Up --json prints successive pretty-printed objects, not one JSON array."""
    decoder = json.JSONDecoder()
    remaining = output.strip()
    while remaining:
        try:
            value, offset = decoder.raw_decode(remaining)
        except ValueError:
            break
        if isinstance(value, dict):
            yield value
        remaining = remaining[offset:].lstrip()


def expected_serve(config, hostname):
    """Accept exactly our proxy, no file server/extra listeners/Funnel."""
    return config == {
        "TCP": {"443": {"HTTPS": True}},
        "Web": {f"{hostname}:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:8743"}}}},
    }


class TailscaleSetup:
    def __init__(self, runner=run_command, clock=monotonic):
        self.run = runner
        self.clock = clock
        self.login = {}
        self.login_until = 0

    async def system(self, *args, checked=True):
        code, output = await self.run(SYSTEMCTL, *args, timeout=20)
        if checked and code:
            raise ValueError("Private connection service could not start; check device diagnostics")
        return code, output

    async def cli(self, *args, checked=True):
        code, output = await self.run(*CLI, *args, timeout=15)
        if checked and code:
            raise ValueError("Private connection needs attention. Check internet access and Tailscale setup instructions")
        return code, output

    async def status(self):
        active, _ = await self.system("is-active", "--quiet", DAEMON, checked=False)
        if active:
            self.login = {}
            return {"state": "off", "command_url": None}
        _, raw = await self.cli("status", "--json", "--peers=false")
        data = json.loads(raw)
        state = data.get("BackendState", "unknown")
        if state not in {"Running", "NeedsLogin", "NeedsMachineAuth", "Stopped", "Starting", "NoState"}:
            state = "unknown"
        hostname = (data.get("Self") or {}).get("DNSName", "").rstrip(".")
        result = {"state": state, "command_url": None}
        if state == "Running" and DNS_NAME.fullmatch(hostname):
            _, raw = await self.cli("serve", "status", "--json")
            gateway_active, _ = await self.system("is-active", "--quiet", GATEWAY, checked=False)
            if expected_serve(json.loads(raw), hostname) and gateway_active == 0:
                result["command_url"] = f"https://{hostname}/command"
        if state != "NeedsLogin" or self.clock() > self.login_until:
            self.login = {}
        return {**result, **self.login}

    async def execute(self, request):
        action = validate_request(request)["action"]
        if action == "status":
            return await self.status()
        if action == "disconnect":
            # Stop ingress first. Identity is retained for intentional reconnection.
            # Even if one stop fails, still attempt the other before reporting.
            self.login = {}
            gateway, _ = await self.system("disable", "--now", GATEWAY, checked=False)
            daemon, _ = await self.system("disable", "--now", DAEMON, checked=False)
            if gateway or daemon:
                raise ValueError("Could not stop every connection service; administrator attention is required")
            return {"state": "off", "command_url": None}
        if action == "connect":
            await self.system("enable", "--now", DAEMON)
            # No --reset, auth key, route, operator, exit node or enrollment tag.
            code, raw = await self.cli("up", "--json", "--timeout=8s", "--hostname=luma",
                                       "--accept-dns=false", "--accept-routes=false", "--ssh=false", checked=False)
            self.login = {}
            for value in json_objects(raw):
                url = value.get("AuthURL", "")
                if isinstance(url, str) and AUTH_URL.fullmatch(url):
                    self.login = {"auth_url": url}
                    qr = value.get("QR", "")
                    if isinstance(qr, str) and PNG_DATA.fullmatch(qr):
                        self.login["qr"] = qr
                    self.login_until = self.clock() + 300
            result = await self.status()
            if code and not self.login and result["state"] not in {"Running", "NeedsMachineAuth"}:
                raise ValueError("Sign-in could not start. Check campus internet access, then try again")
            return result
        # Enable is a separate physical action after HTTPS/account policy setup.
        if (await self.status())["state"] != "Running":
            raise ValueError("Sign in and approve Luma in your Tailscale account first")
        await self.cli("serve", "reset")  # Dedicated Luma daemon; clears any old sharing.
        try:
            await self.system("enable", "--now", GATEWAY)
            await self.cli("serve", "--bg", "--yes", "--https=443", "http://127.0.0.1:8743")
            result = await self.status()
            if not result["command_url"]:
                raise ValueError("HTTPS sharing could not be verified")
            return result
        except (ValueError, OSError, TimeoutError):
            await self.system("disable", "--now", GATEWAY, checked=False)
            raise ValueError("Commands remain off. Enable MagicDNS and HTTPS certificates in Tailscale's DNS settings, then try again") from None


async def tailscale_request(request):
    validate_request(request)
    writer = None
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(SOCKET, limit=65536), 3)
        writer.write(json.dumps(request).encode() + b"\n")
        await writer.drain()
        result = json.loads(await asyncio.wait_for(reader.readline(), 100))
        if "error" in result:
            raise ValueError(result["error"])
        return result
    except (OSError, TimeoutError, json.JSONDecodeError, NotImplementedError):
        raise ValueError("Private connection setup is available only on the installed Pi") from None
    finally:
        if writer:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()


async def serve():
    import pwd
    if os.geteuid() != 0 or os.environ.get("LISTEN_PID") != str(os.getpid()) or os.environ.get("LISTEN_FDS") != "1":
        raise RuntimeError("Start through luma-tailscale-setup.socket")
    owner = pwd.getpwnam("luma").pw_uid
    manager, lock = TailscaleSetup(), asyncio.Lock()

    async def handle(reader, writer):
        result = None
        try:
            peer = writer.get_extra_info("socket").getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            if struct.unpack("3i", peer)[1] != owner:
                return
            request = validate_request(json.loads(await asyncio.wait_for(reader.readline(), 3)))
            if lock.locked():
                result = {"error": "Connection setup is busy; try again shortly"}
            else:
                async with lock:
                    result = await asyncio.wait_for(manager.execute(request), 90)
        except ValueError:
            result = {"error": "Check campus internet, sign-in and Tailscale HTTPS settings, then try again"}
        except Exception:
            result = {"error": "Private connection unavailable; check the local setup service"}
        finally:
            if result is not None:
                with suppress(Exception):
                    writer.write(json.dumps(result).encode() + b"\n")
                    await writer.drain()
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()

    server = await asyncio.start_unix_server(handle, sock=socket.socket(fileno=3), limit=1024)
    async with server:
        await server.serve_forever()


def main():
    asyncio.run(serve())
