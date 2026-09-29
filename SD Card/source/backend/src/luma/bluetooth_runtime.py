"""BlueZ ANCS session; presence requires a bonded, trusted phone and authorized GATT."""
from __future__ import annotations

import asyncio
from contextlib import suppress
import sys
from time import monotonic

from .integrations.ancs import SERVICE, SOURCE, DATA, CONTROL, AttributeResponse, notification, parse_source, request_attributes
from .service import LumaService
from .scene_presence import ScenePresence, evidence


def trusted_connection(properties: dict) -> bool:
    return all(properties.get(key) is True for key in ("Paired", "Bonded", "Trusted", "Connected", "ServicesResolved"))


def plain(properties: dict) -> dict:
    return {key: value.value for key, value in properties.items()}


class BluetoothRuntime:
    def __init__(self, service: LumaService):
        self.service = service
        self.status = "Not configured"
        self.scene_presence = ScenePresence()
        self.scene_authorized = None

    async def scene_presence_worker(self):
        """Independent fresh radio evidence; only sampled for enabled scenes."""
        if sys.platform != 'linux': return
        from dbus_next import BusType
        from dbus_next.aio import MessageBus
        bus = manager = None
        try:
            while True:
                address = self.service.settings.phone_address
                wanted = any(row['enabled'] and row['automatic'] for key, row in self.service.scenes.definitions.items() if key in ('arrive', 'away'))
                if not address or not wanted:
                    self.scene_presence.update(address, None)
                    if bus: bus.disconnect()
                    bus = manager = None
                    await asyncio.sleep(2)
                    continue
                try:
                    async with asyncio.timeout(5):
                        if bus is None:
                            bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
                            intro = await bus.introspect('org.bluez', '/')
                            manager = bus.get_proxy_object('org.bluez', '/', intro).get_interface('org.freedesktop.DBus.ObjectManager')
                        raw = await manager.call_get_managed_objects()
                    objects = {path: {name: plain(props) for name, props in obj.items()} for path, obj in raw.items()}
                    auth = self.scene_authorized
                    authorized = bool(auth and auth[0] == address and 0 <= monotonic() - auth[1] <= 15)
                    self.scene_presence.update(address, evidence(objects, address, authorized=authorized))
                except Exception:
                    self.scene_presence.update(address, None)
                    if bus: bus.disconnect()
                    bus = manager = None
                await asyncio.sleep(2)
        finally:
            self.scene_presence.update('', None)
            if bus: bus.disconnect()

    async def run(self):
        if sys.platform != "linux":
            self.status = "Requires Linux BlueZ"
            return
        while True:
            address = self.service.settings.phone_address
            if address:
                try:
                    await self.session(address)
                except Exception:
                    self.status = "Phone unavailable or notification access not authorized"
                finally:
                    if self.service.state.phone_connected:
                        self.service.phone_disconnected()
            else:
                self.status = "Not configured"
            await asyncio.sleep(10)

    async def session(self, address):
        from dbus_next import BusType, Variant
        from dbus_next.aio import MessageBus

        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        try:
            async def interface(path, name):
                introspection = await asyncio.wait_for(bus.introspect("org.bluez", path), 10)
                return bus.get_proxy_object("org.bluez", path, introspection).get_interface(name)

            manager = await interface("/", "org.freedesktop.DBus.ObjectManager")
            objects = await manager.call_get_managed_objects()
            phone_path = next((path for path, obj in objects.items() if "org.bluez.Device1" in obj and plain(obj["org.bluez.Device1"]).get("Address", "").casefold() == address.casefold()), None)
            if not phone_path:
                raise ValueError("Pair the selected phone first")
            properties = plain(objects[phone_path]["org.bluez.Device1"])
            if not all(properties.get(key) for key in ("Paired", "Bonded", "Trusted")):
                raise ValueError("Phone must be paired, bonded and explicitly trusted")
            device = await interface(phone_path, "org.bluez.Device1")
            if not properties.get("Connected"):
                await asyncio.wait_for(device.call_connect(), 15)
                await asyncio.sleep(2)
            objects = await manager.call_get_managed_objects()
            if not trusted_connection(plain(objects[phone_path]["org.bluez.Device1"])):
                raise ValueError("No resolved trusted connection")
            service_paths = {path for path, obj in objects.items() if "org.bluez.GattService1" in obj and plain(obj["org.bluez.GattService1"]).get("UUID", "").lower() == SERVICE and plain(obj["org.bluez.GattService1"]).get("Device") == phone_path}
            chars = {plain(obj["org.bluez.GattCharacteristic1"])["UUID"].lower(): path for path, obj in objects.items() if "org.bluez.GattCharacteristic1" in obj and plain(obj["org.bluez.GattCharacteristic1"]).get("Service") in service_paths}
            if not {SOURCE, DATA, CONTROL} <= chars.keys():
                raise ValueError("ANCS attributes are unavailable")
            source = await interface(chars[SOURCE], "org.bluez.GattCharacteristic1")
            data = await interface(chars[DATA], "org.bluez.GattCharacteristic1")
            control = await interface(chars[CONTROL], "org.bluez.GattCharacteristic1")
            source_props = await interface(chars[SOURCE], "org.freedesktop.DBus.Properties")
            data_props = await interface(chars[DATA], "org.freedesktop.DBus.Properties")
            phone_props = await interface(phone_path, "org.freedesktop.DBus.Properties")
            notices = asyncio.Queue(maxsize=64)
            fragments = asyncio.Queue(maxsize=64)

            def enqueue(queue, changed):
                if "Value" in changed:
                    if queue.full():
                        queue.get_nowait()
                    queue.put_nowait(bytes(changed["Value"].value))

            source_props.on_properties_changed(lambda name, changed, invalidated: enqueue(notices, changed))
            data_props.on_properties_changed(lambda name, changed, invalidated: enqueue(fragments, changed))
            # Apple requires authorization for these characteristics. Do not unlock
            # on RSSI, an advertisement, or a merely connected unauthenticated device.
            await asyncio.wait_for(data.call_start_notify(), 10)
            await asyncio.wait_for(source.call_start_notify(), 10)
            self.status = "Authorized ANCS session"
            while self.service.settings.phone_address == address:
                props = plain(await asyncio.wait_for(phone_props.call_get_all("org.bluez.Device1"), 5))
                if not trusted_connection(props):
                    break
                # Confirm the ANCS service still exists; iOS may unpublish it.
                current = await asyncio.wait_for(manager.call_get_managed_objects(), 5)
                if chars[SOURCE] not in current:
                    break
                self.service.phone_seen()
                self.scene_authorized = (address, monotonic())
                try:
                    raw = await asyncio.wait_for(notices.get(), 5)
                except asyncio.TimeoutError:
                    continue
                notice = parse_source(raw)
                if notice.event == 2:
                    self.service.remove_notification(str(notice.uid))
                    continue
                # Old notifications re-announced on connection are not new alerts.
                if notice.flags & 4:
                    continue
                while not fragments.empty():
                    fragments.get_nowait()
                parser = AttributeResponse(notice.uid)
                await asyncio.wait_for(control.call_write_value(request_attributes(notice.uid), {"type": Variant("s", "request")}), 5)
                async with asyncio.timeout(5):
                    values = None
                    while values is None:
                        values = parser.feed(await fragments.get())
                self.service.receive_notification(notification(notice, values))
        finally:
            self.scene_authorized = None
            bus.disconnect()
