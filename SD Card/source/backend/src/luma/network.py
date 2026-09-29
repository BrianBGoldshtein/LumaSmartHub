"""Narrow local Wi-Fi broker. NetworkManager owns credentials and persistence.

No shell commands, arbitrary connection dictionaries, or remote-network control.
The socket-activated root process authenticates the caller's Unix peer UID.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import struct
from contextlib import suppress
from uuid import uuid4

from . import eduroam

NM = "org.freedesktop.NetworkManager"
ROOT = "/org/freedesktop/NetworkManager"
SOCKET = "/run/luma-network.sock"
SCAN_TIMEOUT_SECONDS = 12
SCAN_POLL_SECONDS = 0.25


def validate_request(data: object) -> dict:
    if not isinstance(data, dict) or data.get("action") not in {"scan", "enable", "connect", "status", "check"}:
        raise ValueError("Unsupported Wi-Fi operation")
    action = data["action"]
    if action != "connect":
        if set(data) != {"action"}:
            raise ValueError("Invalid Wi-Fi request")
        return data
    fields = {"action", "device", "access_point", "password"}
    if set(data) not in (fields, fields | {"identity"}):
        raise ValueError("Invalid Wi-Fi request")
    if "identity" in data:
        eduroam.validate_identity(data["identity"])
    for field, prefix in [("device", ROOT + "/Devices/"), ("access_point", ROOT + "/AccessPoint/")]:
        value = data[field]
        if not isinstance(value, str) or not value.startswith(prefix) or not value[len(prefix):].isdigit() or len(value) > 120:
            raise ValueError("Select a network from a fresh scan")
    password = data["password"]
    maximum = 256 if "identity" in data else 64
    if not isinstance(password, str) or len(password) > maximum or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in password):
        raise ValueError("Invalid Wi-Fi password")
    if "identity" in data and (not password or len(password.encode("utf-8")) > 256):
        raise ValueError("Invalid SUNet password")
    return data


def security_kind(props: dict) -> str:
    rsn = props.get("RsnFlags", 0)
    # The name is not identity proof: mandatory TLS CA+server matching below
    # protects SUNet credentials. Never downgrade an eduroam-named AP to PSK/open.
    if bytes(props.get("Ssid", b"")) == b"eduroam":
        return "stanford-eduroam" if props.get("Flags", 0) & 1 and rsn & 0x288 == 0x288 else "unsupported"
    # Prefer modern home encryption; other institutions need their own profile.
    if rsn & 0x400:
        return "sae"
    if rsn & 0x100:
        return "wpa-psk"
    if not props.get("Flags", 0) and not rsn and not props.get("WpaFlags", 0):
        return "open"
    return "unsupported"


def connection_settings(props: dict, password: str, identity: str | None = None) -> dict:
    from dbus_next import Variant
    ssid = bytes(props.get("Ssid", b""))
    if not 1 <= len(ssid) <= 32 or props.get("Mode") != 2:
        raise ValueError("Select a visible Wi-Fi network")
    kind = security_kind(props)
    if kind == "unsupported":
        raise ValueError("This network needs advanced setup; use Ethernet or the administrator guide")
    if kind != "stanford-eduroam" and identity is not None:
        raise ValueError("SUNet credentials can only be used with the verified eduroam profile")
    if kind == "wpa-psk" and not (8 <= len(password) <= 63 and password.isascii() or len(password) == 64 and all(c in "0123456789abcdefABCDEF" for c in password)):
        raise ValueError("WPA2 passwords need 8–63 ASCII characters or a 64-digit hexadecimal key")
    if kind == "sae" and not 1 <= len(password.encode("utf-8")) <= 63:
        raise ValueError("WPA3 passwords need 1–63 bytes")
    if kind == "open" and password:
        raise ValueError("An open network does not use a password")
    settings = {
        "connection": {"id": Variant("s", "Luma Wi-Fi"), "uuid": Variant("s", str(uuid4())), "type": Variant("s", "802-11-wireless"), "autoconnect": Variant("b", True)},
        "802-11-wireless": {"ssid": Variant("ay", ssid), "mode": Variant("s", "infrastructure")},
        "ipv4": {"method": Variant("s", "auto")},
        "ipv6": {"method": Variant("s", "auto")},
    }
    if kind == "stanford-eduroam":
        settings["connection"]["id"] = Variant("s", "Luma Stanford eduroam")
        settings["connection"]["autoconnect-priority"] = Variant("i", 20)
        settings["802-11-wireless-security"] = {
            "key-mgmt": Variant("s", "wpa-eap"), "proto": Variant("as", ["rsn"]),
            "pairwise": Variant("as", ["ccmp"]), "group": Variant("as", ["ccmp"]),
        }
        settings["802-1x"] = eduroam.settings(identity, password)
    elif kind != "open":
        settings["802-11-wireless-security"] = {"key-mgmt": Variant("s", kind), "psk": Variant("s", password), "psk-flags": Variant("u", 0)}
    return settings


class NetworkManager:
    def __init__(self, bus):
        self.bus = bus

    async def interface(self, path, name):
        introspection = await asyncio.wait_for(self.bus.introspect(NM, path), 5)
        return self.bus.get_proxy_object(NM, path, introspection).get_interface(name)

    async def properties(self, path, name):
        proxy = await self.interface(path, "org.freedesktop.DBus.Properties")
        return {key: value.value for key, value in (await asyncio.wait_for(proxy.call_get_all(name), 5)).items()}

    async def wait_for_scan(self, device, previous_scan):
        """Wait for NetworkManager's LastScan to advance, not an arbitrary delay."""
        deadline = asyncio.get_running_loop().time() + SCAN_TIMEOUT_SECONDS
        while asyncio.get_running_loop().time() < deadline:
            current = await self.properties(device, NM + ".Device.Wireless")
            last_scan = current.get("LastScan", -1)
            if last_scan >= 0 and last_scan != previous_scan:
                return True
            await asyncio.sleep(SCAN_POLL_SECONDS)
        return False

    async def status(self, recheck=False):
        if recheck:
            manager = await self.interface(ROOT, NM)
            await asyncio.wait_for(manager.call_check_connectivity(), 25)
        props = await self.properties(ROOT, NM)
        enabled = bool(props.get("ConnectivityCheckAvailable") and props.get("ConnectivityCheckEnabled"))
        # Without a probe NM can report FULL from a default route alone.
        # Never present that as verified internet access.
        state = {1: "offline", 2: "portal", 3: "limited", 4: "online"}.get(props.get("Connectivity"), "unknown") if enabled else "unknown"
        if props.get("State") in {10, 20}:
            state = "offline"
        return {"state": state, "checking_enabled": enabled}

    async def scan(self, refresh=True):
        manager = await self.interface(ROOT, NM)
        state = await self.properties(ROOT, NM)
        networks = []
        wifi_devices = 0
        scan_complete = False
        for device in await manager.call_get_devices():
            props = await self.properties(device, NM + ".Device")
            if props.get("DeviceType") != 2:
                continue
            wifi_devices += 1
            wireless = await self.interface(device, NM + ".Device.Wireless")
            if refresh and state.get("WirelessEnabled"):
                before = await self.properties(device, NM + ".Device.Wireless")
                previous_scan = before.get("LastScan", -1)
                with suppress(Exception):
                    await asyncio.wait_for(wireless.call_request_scan({}), 5)
                # RequestScan is asynchronous. Do not tell the owner the radio
                # saw no networks until NetworkManager reports completion.
                with suppress(Exception):
                    scan_complete = scan_complete or await self.wait_for_scan(device, previous_scan)
            wifi = await self.properties(device, NM + ".Device.Wireless")
            for path in await wireless.call_get_access_points():
                ap = await self.properties(path, NM + ".AccessPoint")
                ssid = bytes(ap.get("Ssid", b""))
                if not ssid or ap.get("Mode") != 2:
                    continue
                networks.append({"device": device, "access_point": path, "ssid": ssid.decode("utf-8", errors="replace"), "security": security_kind(ap), "strength": ap.get("Strength", 0), "connected": wifi.get("ActiveAccessPoint") == path})
        networks.sort(key=lambda ap: (not ap["connected"], -ap["strength"]))
        return {"wifi_enabled": bool(state.get("WirelessEnabled")), "hardware_enabled": bool(state.get("WirelessHardwareEnabled")), "connectivity": state.get("Connectivity", 0), "wifi_device_count": wifi_devices, "scan_complete": scan_complete, "networks": networks[:80]}

    async def connect(self, request):
        from dbus_next import Variant
        device, ap = request["device"], request["access_point"]
        available = await self.scan(refresh=False)
        if not any(item["device"] == device and item["access_point"] == ap for item in available["networks"]):
            raise ValueError("That network is no longer visible; scan again")
        props = await self.properties(ap, NM + ".AccessPoint")
        settings = connection_settings(props, request["password"], request.get("identity"))
        if security_kind(props) != "stanford-eduroam" and any(item["access_point"] == ap and item["connected"] for item in available["networks"]):
            return {"connected": True, "already_connected": True}
        manager = await self.interface(ROOT, NM)
        profile, active, _ = await manager.call_add_and_activate_connection2(settings, device, ap, {"persist": Variant("s", "memory")})
        saved = False
        try:
            for _ in range(45):
                state = await self.properties(active, NM + ".Connection.Active")
                if state.get("State") == 2:
                    connection = await self.interface(profile, NM + ".Settings.Connection")
                    await connection.call_save()
                    saved = True
                    return {"connected": True, "already_connected": False}
                if state.get("State") == 4:
                    break
                await asyncio.sleep(1)
            raise ValueError("Could not join. Check the password, signal and router; your previous saved networks are retained")
        finally:
            if not saved:
                with suppress(Exception):
                    connection = await self.interface(profile, NM + ".Settings.Connection")
                    await asyncio.wait_for(connection.call_delete(), 5)

    async def execute(self, request):
        from dbus_next import Variant
        validate_request(request)
        if request["action"] in {"status", "check"}:
            return await self.status(recheck=request["action"] == "check")
        if request["action"] == "connect":
            return await self.connect(request)
        if request["action"] == "enable":
            props = await self.interface(ROOT, "org.freedesktop.DBus.Properties")
            await props.call_set(NM, "WirelessEnabled", Variant("b", True))
        return await self.scan()


async def network_request(request: dict) -> dict:
    validate_request(request)
    if not hasattr(asyncio, "open_unix_connection"):
        raise ValueError("Wi-Fi setup requires the Linux appliance network service")
    writer = None
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(SOCKET, limit=65536), 3)
        writer.write(json.dumps(request).encode() + b"\n")
        await writer.drain()
        raw = await asyncio.wait_for(reader.readline(), 80)
        result = json.loads(raw)
        if "error" in result:
            raise ValueError(result["error"])
        return result
    except (OSError, TimeoutError, json.JSONDecodeError, NotImplementedError):
        raise ValueError("Wi-Fi setup is unavailable. Use Ethernet or check the local network service") from None
    finally:
        if writer:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()


async def serve():
    import pwd
    from dbus_next import BusType
    from dbus_next.aio import MessageBus
    if os.geteuid() != 0 or os.environ.get("LISTEN_PID") != str(os.getpid()) or os.environ.get("LISTEN_FDS") != "1":
        raise RuntimeError("Start through luma-network.socket")
    owner = pwd.getpwnam("luma").pw_uid
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    manager = NetworkManager(bus)
    lock = asyncio.Lock()

    async def handle(reader, writer):
        try:
            peer = writer.get_extra_info("socket").getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            if struct.unpack("3i", peer)[1] != owner:
                return
            data = validate_request(json.loads(await asyncio.wait_for(reader.readline(), 3)))
            if lock.locked():
                result = {"error": "Wi-Fi setup is busy; try again shortly"}
            else:
                async with lock:
                    result = await asyncio.wait_for(manager.execute(data), 70)
        except ValueError:
            # Never forward third-party exception text or credential fragments.
            result = {"error": "Invalid network selection or password. Scan again and check the entered details"}
        except Exception:
            result = {"error": "Wi-Fi operation failed. Check the password, radio and network service"}
        finally:
            if "result" in locals():
                with suppress(Exception):
                    writer.write(json.dumps(result).encode() + b"\n")
                    await writer.drain()
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()

    listener = socket.socket(fileno=3)
    server = await asyncio.start_unix_server(handle, sock=listener, limit=2048)
    try:
        async with server:
            await server.serve_forever()
    finally:
        bus.disconnect()


def main():
    asyncio.run(serve())
