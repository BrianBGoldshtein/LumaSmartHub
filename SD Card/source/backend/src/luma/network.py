"""Narrow local Wi-Fi broker. NetworkManager owns credentials and persistence.

No shell commands, arbitrary connection dictionaries, or remote-network control.
The socket-activated root process authenticates the caller's Unix peer UID.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import struct
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from . import eduroam

NM = "org.freedesktop.NetworkManager"
ROOT = "/org/freedesktop/NetworkManager"
SOCKET = "/run/luma-network.sock"
SCAN_TIMEOUT_SECONDS = 12
SCAN_POLL_SECONDS = 0.25
HOTSPOT_SSID = "Luma-Devices"
HOTSPOT_UUID = "92a6cc9f-98d5-4dc4-a499-1c85e87da2b8"
WIFI_CAP_AP = 0x40
WIFI_CAP_FREQ_VALID = 0x100
WIFI_CAP_FREQ_2GHZ = 0x200


def validate_request(data: object) -> dict:
    actions = {"scan", "enable", "connect", "status", "check", "hotspot-status", "hotspot-start", "hotspot-stop"}
    if not isinstance(data, dict) or data.get("action") not in actions:
        raise ValueError("Unsupported Wi-Fi operation")
    action = data["action"]
    if action not in {"connect", "hotspot-start"}:
        if set(data) != {"action"}:
            raise ValueError("Invalid Wi-Fi request")
        return data
    if action == "hotspot-start":
        if set(data) != {"action", "password", "same_as_pin"} or not isinstance(data["same_as_pin"], bool):
            raise ValueError("Invalid Wi-Fi request")
        password = data["password"]
        if not isinstance(password, str) or not 8 <= len(password) <= 63 or not password.isascii() or any(ord(char) < 32 or ord(char) == 127 for char in password):
            raise ValueError("The Wi-Fi key must contain 8–63 ASCII characters")
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


def hotspot_connection_settings(password: str, interface_name: str, same_as_pin: bool = True) -> dict:
    """Fixed 2.4 GHz WPA2/NAT profile for a separately attached Wi-Fi radio."""
    from dbus_next import Variant

    if not isinstance(password, str) or not 8 <= len(password) <= 63 or not password.isascii() or any(ord(char) < 32 or ord(char) == 127 for char in password):
        raise ValueError("The Wi-Fi key must contain 8–63 ASCII characters")
    if not isinstance(interface_name, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,15}", interface_name):
        raise ValueError("A supported Wi-Fi adapter is required")
    return {
        "connection": {
            "id": Variant("s", "Luma Levoit 2.4 GHz [PIN]" if same_as_pin else "Luma Levoit 2.4 GHz [separate key]"),
            "uuid": Variant("s", HOTSPOT_UUID),
            "type": Variant("s", "802-11-wireless"),
            "interface-name": Variant("s", interface_name),
            "autoconnect": Variant("b", True),
            "autoconnect-priority": Variant("i", -10),
        },
        "802-11-wireless": {
            "ssid": Variant("ay", HOTSPOT_SSID.encode("ascii")),
            "mode": Variant("s", "ap"),
            "band": Variant("s", "bg"),
            "channel": Variant("u", 6),
        },
        "802-11-wireless-security": {
            "key-mgmt": Variant("s", "wpa-psk"),
            "psk": Variant("s", password),
            "psk-flags": Variant("u", 0),
            "proto": Variant("as", ["rsn"]),
            "pairwise": Variant("as", ["ccmp"]),
            "group": Variant("as", ["ccmp"]),
        },
        "ipv4": {"method": Variant("s", "shared")},
        "ipv6": {"method": Variant("s", "disabled")},
    }


def wifi_phy(interface_name: str) -> str | None:
    """Return a Linux wireless PHY identity, rejecting virtual same-radio APs."""
    if not isinstance(interface_name, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,15}", interface_name):
        return None
    try:
        return Path("/sys/class/net", interface_name, "phy80211").resolve(strict=True).name
    except OSError:
        return None


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

    async def wifi_radios(self):
        manager = await self.interface(ROOT, NM)
        radios = []
        for path in await manager.call_get_devices():
            device = await self.properties(path, NM + ".Device")
            if device.get("DeviceType") != 2:
                continue
            wireless = await self.properties(path, NM + ".Device.Wireless")
            interface_name = device.get("Interface")
            capabilities = wireless.get("WirelessCapabilities", 0)
            has_2ghz = not capabilities & WIFI_CAP_FREQ_VALID or bool(capabilities & WIFI_CAP_FREQ_2GHZ)
            radios.append({
                "path": path,
                "name": interface_name,
                "phy": wifi_phy(interface_name),
                "can_ap": bool(capabilities & WIFI_CAP_AP) and has_2ghz,
                "station": device.get("State") == 100 and wireless.get("Mode") == 2 and wireless.get("ActiveAccessPoint") not in (None, "/"),
            })
        return radios

    async def hotspot_profile(self):
        settings = await self.interface(ROOT + "/Settings", NM + ".Settings")
        for path in await settings.call_list_connections():
            connection = await self.interface(path, NM + ".Settings.Connection")
            try:
                profile = await connection.call_get_settings()
            except Exception:
                continue
            section = profile.get("connection", {})
            uid = section.get("uuid")
            if getattr(uid, "value", None) == HOTSPOT_UUID:
                return path
        return None

    async def hotspot_uses_pin(self, profile):
        connection = await self.interface(profile, NM + ".Settings.Connection")
        settings = await connection.call_get_settings()
        profile_id = settings.get("connection", {}).get("id")
        return getattr(profile_id, "value", None) == "Luma Levoit 2.4 GHz [PIN]"

    async def hotspot_status(self):
        radios = await self.wifi_radios()
        stations = [radio for radio in radios if radio["station"]]
        ap_candidates = [
            radio for radio in radios
            if radio["can_ap"] and radio["phy"] and not radio["station"]
            and all(radio["phy"] != station["phy"] for station in stations)
        ]
        profile = await self.hotspot_profile()
        active = False
        same_as_pin = await self.hotspot_uses_pin(profile) if profile else None
        if profile:
            manager_props = await self.properties(ROOT, NM)
            for active_path in manager_props.get("ActiveConnections", []):
                with suppress(Exception):
                    state = await self.properties(active_path, NM + ".Connection.Active")
                    if state.get("Connection") == profile and state.get("State") == 2:
                        active = True
                        break
        if not stations:
            reason = "Connect Luma to eduroam or another Wi-Fi network first."
        elif not ap_candidates:
            reason = "A second, Linux-supported USB Wi-Fi adapter is needed; keep the Pi's built-in radio on eduroam."
        else:
            reason = "Ready to share the current internet connection over 2.4 GHz Wi-Fi."
        return {
            "ssid": HOTSPOT_SSID,
            "configured": profile is not None,
            "active": active,
            "same_as_pin": same_as_pin,
            "upstream_connected": bool(stations),
            "can_enable": bool(stations and ap_candidates),
            "reason": reason,
        }

    async def stop_hotspot(self):
        profile = await self.hotspot_profile()
        if profile is None:
            return await self.hotspot_status()
        manager = await self.interface(ROOT, NM)
        manager_props = await self.properties(ROOT, NM)
        for active_path in manager_props.get("ActiveConnections", []):
            with suppress(Exception):
                active = await self.properties(active_path, NM + ".Connection.Active")
                if active.get("Connection") == profile:
                    await manager.call_deactivate_connection(active_path)
                    break
        connection = await self.interface(profile, NM + ".Settings.Connection")
        await connection.call_delete()
        return await self.hotspot_status()

    async def start_hotspot(self, password: str, same_as_pin: bool):
        from dbus_next import Variant

        status = await self.hotspot_status()
        if not status["can_enable"]:
            raise ValueError(status["reason"])
        radios = await self.wifi_radios()
        stations = [radio for radio in radios if radio["station"]]
        candidates = [
            radio for radio in radios
            if radio["can_ap"] and radio["phy"] and not radio["station"]
            and all(radio["phy"] != station["phy"] for station in stations)
        ]
        if not candidates:
            raise ValueError("A separate 2.4 GHz Wi-Fi adapter is required")

        # Replace only Luma's own saved AP profile so changing the Luma PIN
        # also rotates the network key. Never touch the eduroam profile.
        await self.stop_hotspot()
        manager = await self.interface(ROOT, NM)
        settings = hotspot_connection_settings(password, candidates[0]["name"], same_as_pin)
        profile, active, _ = await manager.call_add_and_activate_connection2(
            settings, candidates[0]["path"], "/", {"persist": Variant("s", "memory")}
        )
        saved = False
        try:
            for _ in range(45):
                state = await self.properties(active, NM + ".Connection.Active")
                if state.get("State") == 2:
                    connection = await self.interface(profile, NM + ".Settings.Connection")
                    await connection.call_save()
                    saved = True
                    return await self.hotspot_status()
                if state.get("State") == 4:
                    break
                await asyncio.sleep(1)
            raise ValueError("Could not start the hotspot. Check the USB Wi-Fi adapter and its 2.4 GHz AP support")
        finally:
            if not saved:
                with suppress(Exception):
                    connection = await self.interface(profile, NM + ".Settings.Connection")
                    await asyncio.wait_for(connection.call_delete(), 5)

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
        if request["action"] == "hotspot-status":
            return await self.hotspot_status()
        if request["action"] == "hotspot-start":
            return await self.start_hotspot(request["password"], request["same_as_pin"])
        if request["action"] == "hotspot-stop":
            return await self.stop_hotspot()
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
