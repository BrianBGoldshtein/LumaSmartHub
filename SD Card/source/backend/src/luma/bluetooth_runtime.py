"""BlueZ ANCS session; presence requires a bonded, trusted phone and authorized GATT."""
from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
import sys
from time import monotonic

from .integrations.ancs import SERVICE, SOURCE, DATA, CONTROL, AttributeResponse, notification, parse_source, request_attributes
from .service import LumaService
from .scene_presence import ScenePresence, evidence

SERVICE_CHANGED = '00002a05-0000-1000-8000-00805f9b34fb'


def trusted_connection(properties: dict) -> bool:
    return all(properties.get(key) is True for key in ("Paired", "Bonded", "Trusted", "Connected", "ServicesResolved"))


def plain(properties: dict) -> dict:
    return {key: value.value for key, value in properties.items()}


class BluetoothStatusError(Exception):
    """A fixed, user-safe explanation; never include BlueZ exception text."""


async def scan_for_paired_phone(manager, adapter, phone_path: str, *, pause=asyncio.sleep) -> bool:
    """Briefly refresh BlueZ's LE view before a normal bonded reconnect.

    Discovery is only a hint that a device may be reachable. It never changes
    the saved bond or grants presence; ANCS authorization is checked later.
    BlueZ tracks discovery sessions by D-Bus caller, so stopping ours leaves
    the pairing wizard's independent discovery session intact.
    """
    from dbus_next import Variant

    await asyncio.wait_for(adapter.call_set_discovery_filter({
        "Transport": Variant("s", "le"), "DuplicateData": Variant("b", False),
    }), 5)
    await asyncio.wait_for(adapter.call_start_discovery(), 5)
    try:
        for _ in range(6):
            await pause(0.5)
            objects = await asyncio.wait_for(manager.call_get_managed_objects(), 5)
            device = objects.get(phone_path, {}).get("org.bluez.Device1")
            if device and plain(device).get("Connected") is True:
                return True
        return False
    finally:
        with suppress(Exception):
            await asyncio.wait_for(adapter.call_stop_discovery(), 5)


async def wait_for_trusted_connection(manager, phone_path: str, *, timeout: float = 12) -> dict:
    """BlueZ can report Connected before iOS GATT service discovery finishes."""
    deadline = monotonic() + timeout
    while True:
        objects = await manager.call_get_managed_objects()
        device = objects.get(phone_path, {}).get("org.bluez.Device1")
        if device is None:
            raise BluetoothStatusError("Saved iPhone bond is missing from Bluetooth")
        properties = plain(device)
        if trusted_connection(properties):
            return objects
        if not all(properties.get(key) is True for key in ("Paired", "Bonded", "Trusted")):
            raise BluetoothStatusError("iPhone bond or trust was lost")
        if not properties.get("Connected"):
            raise BluetoothStatusError("iPhone Bluetooth link is disconnected")
        if monotonic() >= deadline:
            raise BluetoothStatusError("iPhone connected; waiting for Bluetooth services")
        await asyncio.sleep(0.5)


def ancs_characteristics(objects: dict, phone_path: str) -> dict[str,str]:
    services={path for path,obj in objects.items()
              if 'org.bluez.GattService1' in obj
              and plain(obj['org.bluez.GattService1']).get('UUID','').lower()==SERVICE
              and plain(obj['org.bluez.GattService1']).get('Device')==phone_path}
    return {plain(obj['org.bluez.GattCharacteristic1'])['UUID'].lower():path
            for path,obj in objects.items() if 'org.bluez.GattCharacteristic1' in obj
            and plain(obj['org.bluez.GattCharacteristic1']).get('Service') in services}


async def wait_for_ancs(manager,phone_path: str,*,initial=None,timeout=30,pause=asyncio.sleep):
    """ANCS can appear after GATT resolution or reappear on an existing link."""
    deadline=monotonic()+timeout
    objects=initial
    while True:
        if objects is None:objects=await asyncio.wait_for(manager.call_get_managed_objects(),5)
        device=objects.get(phone_path,{}).get('org.bluez.Device1')
        if device is None or not trusted_connection(plain(device)):
            raise BluetoothStatusError('iPhone Bluetooth link or services disconnected')
        chars=ancs_characteristics(objects,phone_path)
        if {SOURCE,DATA,CONTROL}<=chars.keys():return objects,chars
        if monotonic()>=deadline:
            raise BluetoothStatusError('iPhone connected, but notification service is unavailable')
        await pause(1)
        objects=None


def service_changed_path(objects: dict,phone_path: str) -> str | None:
    services={path for path,obj in objects.items() if 'org.bluez.GattService1' in obj
              and plain(obj['org.bluez.GattService1']).get('Device')==phone_path}
    return next((path for path,obj in objects.items() if 'org.bluez.GattCharacteristic1' in obj
                 and plain(obj['org.bluez.GattCharacteristic1']).get('Service') in services
                 and plain(obj['org.bluez.GattCharacteristic1']).get('UUID','').lower()==SERVICE_CHANGED),None)


class BluetoothRuntime:
    def __init__(self, service: LumaService):
        self.service = service
        self.status = "Not configured"
        self.scene_presence = ScenePresence()
        self.scene_authorized = None
        self.last_discovery = -60.0
        self.last_reconnect_at: str | None = None
        self.reconnect_attempts = 0

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

    async def run(self,*,pause=asyncio.sleep,retry_seconds=10):
        if sys.platform != "linux":
            self.status = "Requires Linux BlueZ"
            return
        while True:
            address = self.service.settings.phone_address
            if address:
                try:
                    self.status = "Checking iPhone Bluetooth connection"
                    await self.session(address)
                except BluetoothStatusError as exc:
                    self.status = str(exc)
                except Exception:
                    self.status = "Bluetooth session failed; retrying"
                finally:
                    if self.service.state.phone_connected:
                        self.service.phone_disconnected()
            else:
                self.status = "Not configured"
            await pause(retry_seconds)

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
                raise BluetoothStatusError("Saved iPhone bond is missing from Bluetooth")
            properties = plain(objects[phone_path]["org.bluez.Device1"])
            if not all(properties.get(key) for key in ("Paired", "Bonded", "Trusted")):
                raise BluetoothStatusError("iPhone bond or trust was lost")
            device = await interface(phone_path, "org.bluez.Device1")
            if not properties.get("Connected"):
                if monotonic() - self.last_discovery >= 45:
                    self.last_discovery = monotonic()
                    adapter_path = next((path for path, obj in objects.items() if "org.bluez.Adapter1" in obj), None)
                    if adapter_path:
                        self.status = "Looking for paired iPhone"
                        try:
                            adapter = await interface(adapter_path, "org.bluez.Adapter1")
                            await scan_for_paired_phone(manager, adapter, phone_path)
                        except Exception:
                            # Some controllers cannot scan while another radio
                            # operation is active. Still attempt the direct bond.
                            pass
                        objects = await manager.call_get_managed_objects()
                        properties = plain(objects.get(phone_path, {}).get("org.bluez.Device1", {}))
                if not all(properties.get(key) for key in ("Paired", "Bonded", "Trusted")):
                    raise BluetoothStatusError("iPhone bond or trust was lost")
            if not properties.get("Connected"):
                self.status = "Reconnecting to paired iPhone"
                self.last_reconnect_at = datetime.now(UTC).isoformat()
                self.reconnect_attempts += 1
                try:
                    await asyncio.wait_for(device.call_connect(), 15)
                except Exception as exc:
                    raise BluetoothStatusError("iPhone Bluetooth link is disconnected; Luma will retry automatically") from exc
            objects = await wait_for_trusted_connection(manager, phone_path)
            changed=service_changed_path(objects,phone_path)
            if changed:
                try:
                    characteristic=await interface(changed,'org.bluez.GattCharacteristic1')
                    await asyncio.wait_for(characteristic.call_start_notify(),5)
                except Exception:
                    # BlueZ may already subscribe internally; periodic GATT
                    # discovery below remains the fallback.
                    pass
            self.status='iPhone connected; waiting for notification service'
            objects,chars=await wait_for_ancs(manager,phone_path,initial=objects)
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
            try:
                await asyncio.wait_for(data.call_start_notify(), 10)
                await asyncio.wait_for(source.call_start_notify(), 10)
            except Exception as exc:
                raise BluetoothStatusError("iPhone notification authorization was not confirmed") from exc
            self.status = "Authorized ANCS session"
            while self.service.settings.phone_address == address:
                props = plain(await asyncio.wait_for(phone_props.call_get_all("org.bluez.Device1"), 5))
                if not trusted_connection(props):
                    self.status = "iPhone Bluetooth link or services disconnected"
                    break
                # Confirm the ANCS service still exists; iOS may unpublish it.
                current = await asyncio.wait_for(manager.call_get_managed_objects(), 5)
                if chars[SOURCE] not in current:
                    self.status = "iPhone notification service disappeared"
                    break
                self.service.phone_seen()
                self.scene_authorized = (address, monotonic())
                try:
                    raw = await asyncio.wait_for(notices.get(), 5)
                except asyncio.TimeoutError:
                    continue
                try:
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
                except (ValueError, asyncio.TimeoutError):
                    # One malformed/stale notice must not tear down an otherwise
                    # authorized iPhone link or force the screen into standby.
                    continue
        finally:
            self.scene_authorized = None
            bus.disconnect()
