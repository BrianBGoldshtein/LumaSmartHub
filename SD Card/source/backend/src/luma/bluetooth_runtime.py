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
from .ancs_advertising import ANCSReconnectAdvertising
from .companion_presence import AuthorizedPhoneSession

SERVICE_CHANGED = '00002a05-0000-1000-8000-00805f9b34fb'


def trusted_connection(properties: dict) -> bool:
    return all(properties.get(key) is True for key in ("Paired", "Bonded", "Trusted", "Connected", "ServicesResolved"))


def trusted_link(properties: dict) -> bool:
    """A bond and live link are necessary; ANCS subscription proves authorization."""
    return all(properties.get(key) is True for key in ("Paired", "Bonded", "Trusted", "Connected"))


def plain(properties: dict) -> dict:
    return {key: value.value for key, value in properties.items()}


class BluetoothStatusError(Exception):
    """A fixed, user-safe explanation; never include BlueZ exception text."""


async def scan_for_paired_phone(manager, adapter, phone_path: str, *, phone_address: str | None = None,
                                pause=asyncio.sleep, connect=None,
                                address_is_current=lambda: True) -> bool:
    """Briefly refresh BlueZ's LE view before a normal bonded reconnect.

    Discovery is only a hint that a device may be reachable. It never changes
    the saved bond or grants presence; ANCS authorization is checked later.
    BlueZ tracks discovery sessions by D-Bus caller, so stopping ours leaves
    the pairing wizard's independent discovery session intact.
    """
    from dbus_next import Variant

    basic_filter = {
        "Transport": Variant("s", "le"), "DuplicateData": Variant("b", False),
    }
    if phone_address:
        # BlueZ can initiate a connection as soon as the selected, bonded
        # iPhone advertises. A full address pattern excludes other phones.
        try:
            await asyncio.wait_for(adapter.call_set_discovery_filter({
                **basic_filter, "Pattern": Variant("s", phone_address),
                # Do not let BlueZ initiate a second competing request when
                # this caller owns the explicit, bounded Connect below.
                "AutoConnect": Variant("b", connect is None),
            }), 5)
        except Exception:
            # Older BlueZ builds may reject AutoConnect. Preserve the LE scan
            # and explicit Device1.Connect path rather than losing both.
            await asyncio.wait_for(adapter.call_set_discovery_filter(basic_filter), 5)
    else:
        await asyncio.wait_for(adapter.call_set_discovery_filter(basic_filter), 5)
    await asyncio.wait_for(adapter.call_start_discovery(), 5)
    try:
        for _ in range(12):
            await pause(0.5)
            if not address_is_current():
                return False
            objects = await asyncio.wait_for(manager.call_get_managed_objects(), 5)
            device = objects.get(phone_path, {}).get("org.bluez.Device1")
            if device and plain(device).get("Connected") is True:
                return True
        if connect is not None and address_is_current():
            # LE Connect needs a fresh scan report. Keep this caller's scan
            # running while it connects, instead of stopping just before it.
            values = plain(device) if device else {}
            if all(values.get(key) is True for key in ('Paired', 'Bonded', 'Trusted')):
                # Runtime callback bounds the request plus pending-operation
                # cleanup. Give cleanup room before stopping this scan.
                await asyncio.wait_for(connect(), 35)
                return True  # Link request only, NOT presence/authorization.
        return False
    finally:
        with suppress(Exception):
            await asyncio.wait_for(adapter.call_stop_discovery(), 5)


async def wait_for_trusted_connection(manager, phone_path: str, *, timeout: float = 12,
                                      query_timeout: float = 5) -> dict:
    """BlueZ can report Connected before iOS GATT service discovery finishes."""
    deadline = monotonic() + timeout
    while True:
        # A stuck BlueZ ObjectManager reply must not strand the reconnect
        # worker forever. Let the outer loop release this bus and retry.
        objects = await asyncio.wait_for(manager.call_get_managed_objects(), query_timeout)
        device = objects.get(phone_path, {}).get("org.bluez.Device1")
        if device is None:
            raise BluetoothStatusError("Saved iPhone bond is missing from Bluetooth")
        properties = plain(device)
        # Some BlueZ builds export GATT objects before ServicesResolved flips.
        # Do not equate this with presence: subscribing to ANCS is still required.
        if trusted_connection(properties) or (trusted_link(properties)
                                              and SOURCE in ancs_characteristics(objects, phone_path)):
            return objects
        if not all(properties.get(key) is True for key in ("Paired", "Bonded", "Trusted")):
            raise BluetoothStatusError("iPhone bond or trust was lost")
        if not properties.get("Connected"):
            raise BluetoothStatusError("iPhone Bluetooth link is disconnected")
        if monotonic() >= deadline:
            raise BluetoothStatusError("iPhone connected; waiting for Bluetooth services")
        await asyncio.sleep(0.5)


async def connect_paired_phone(manager, device, phone_path: str, *,
                               address_is_current=lambda: True, timeout: float = 15) -> None:
    """One bounded request; cancel only our unfinished D-Bus wait.

    Cancelling a Python D-Bus wait does NOT cancel the radio operation.
    Device1.Disconnect is BlueZ's documented cancellation mechanism. Re-read
    the selected bond first so a completed/manual link is left alone, and
    never remove a bond or grant presence here.
    """
    async def current_properties():
        objects = await asyncio.wait_for(manager.call_get_managed_objects(), 5)
        return plain(objects.get(phone_path, {}).get('org.bluez.Device1', {}))

    def selected_bond(props):
        return address_is_current() and all(props.get(key) is True
                                           for key in ('Paired', 'Bonded', 'Trusted'))

    before = await current_properties()
    if not selected_bond(before):
        raise BluetoothStatusError('Selected iPhone or its bond changed before reconnect')
    if before.get('Connected') is True:
        return
    try:
        await asyncio.wait_for(device.call_connect(), timeout)
    except (Exception, asyncio.CancelledError) as exc:
        # A terminal BlueZ error (especially InProgress) does not establish
        # ownership of its pending radio operation. Disconnecting then can
        # cancel an incoming/manual connection or another caller's request.
        # Only a timeout/cancellation of this wait requires explicit cleanup.
        cancel_pending = isinstance(exc, (asyncio.TimeoutError, asyncio.CancelledError))
        fresh = None
        with suppress(Exception):
            fresh = await current_properties()
        if fresh is not None and selected_bond(fresh):
            if fresh.get('Connected') is True and not isinstance(exc, asyncio.CancelledError):
                return
            if fresh.get('Connected') is not True and cancel_pending:
                with suppress(Exception):
                    await asyncio.wait_for(device.call_disconnect(), 5)
        if isinstance(exc, asyncio.CancelledError):
            raise
        raise BluetoothStatusError(
            'iPhone reconnect did not finish; Luma will retry automatically') from exc


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
        if device is None or not trusted_link(plain(device)):
            raise BluetoothStatusError('iPhone Bluetooth link or services disconnected')
        chars=ancs_characteristics(objects,phone_path)
        # Apple's ANCS specification requires Notification Source; Data Source
        # and Control Point are optional. Source notification authorization is
        # sufficient for the privacy key, but not for caller/title details.
        if SOURCE in chars:return objects,chars
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


async def subscribe_ancs(source, data=None) -> bool:
    """Subscribe to mandatory authorized source; optional data may degrade."""
    try:
        await asyncio.wait_for(source.call_start_notify(), 10)
    except Exception as exc:
        raise BluetoothStatusError("iPhone notification authorization was not confirmed") from exc
    if data is not None:
        try:
            await asyncio.wait_for(data.call_start_notify(), 10)
        except Exception:
            return False
    return data is not None


class BluetoothRuntime:
    def __init__(self, service: LumaService, *, coordinator=None, profile_id='primary'):
        self.service = service
        self.coordinator, self.profile_id = coordinator, profile_id
        self.status = "Not configured"
        self.scene_presence = ScenePresence()
        self.scene_authorized = None
        self.remote_authorized = AuthorizedPhoneSession()
        self.last_discovery = -60.0
        self.last_reconnect_at: str | None = None
        self.reconnect_attempts = 0
        self.last_service_recovery = -300.0
        self.last_service_recovery_at: str | None = None
        self.service_recovery_attempts = 0
        self.advertiser = ANCSReconnectAdvertising(lambda: self.service.settings.phone_address)

    @property
    def advertising_status(self):
        return self.advertiser.status

    def companion_presence(self):
        return self.remote_authorized.snapshot(self.service.settings.phone_address,
                                              phone_connected=self.service.state.phone_connected)

    async def reconnect_advertising_worker(self):
        await self.advertiser.run()

    async def refresh_phone_services(self, manager, device, device_props, phone_path,
                                     adapter, address: str) -> None:
        """One bounded repair per five minutes for a still-selected iPhone."""
        if monotonic() - self.last_service_recovery < 300 or self.service.settings.phone_address != address:
            raise BluetoothStatusError("iPhone services are unavailable; Luma will retry automatically")
        self.last_service_recovery = monotonic()
        self.last_service_recovery_at = datetime.now(UTC).isoformat()
        self.service_recovery_attempts += 1
        self.status = "Refreshing stalled iPhone Bluetooth services"
        async def recover():
            await recover_stalled_services(manager, device, device_props, phone_path,
                                          adapter=adapter,
                                          address_is_current=lambda: self.service.settings.phone_address == address)
        if self.coordinator:
            # This appliance uses one adapter. Serialize this phone's repair
            # with other outgoing jobs, never restart the adapter or peers.
            await self.coordinator.perform(self.profile_id, 'hci0', recover)
        else:
            await recover()

    async def _scan_phone(self, manager, adapter, phone_path, address, device):
        async def connect():
            return await connect_paired_phone(manager, device, phone_path,
                address_is_current=lambda: self.service.settings.phone_address == address)
        async def scan():
            return await scan_for_paired_phone(manager, adapter, phone_path,
                # A shared LE scan refreshes all registered phones, without
                # inviting unpaired devices or granting RSSI-based presence.
                phone_address=None if self.coordinator else address, connect=connect,
                address_is_current=lambda: self.service.settings.phone_address == address)
        if self.coordinator:
            return await self.coordinator.perform(self.profile_id, 'hci0', scan, scan=True, connect=connect)
        return await scan()

    async def _connect_phone(self, manager, device, phone_path, address):
        async def connect():
            return await connect_paired_phone(manager, device, phone_path,
                address_is_current=lambda: self.service.settings.phone_address == address)
        if self.coordinator:
            return await self.coordinator.perform(self.profile_id, 'hci0', connect)
        return await connect()

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
            await pause(self.coordinator.failure_delay(self.profile_id) if self.coordinator and address else retry_seconds)

    async def session(self, address):
        from dbus_next import BusType, Variant
        from dbus_next.aio import MessageBus

        bus = MessageBus(bus_type=BusType.SYSTEM)
        try:
            await asyncio.wait_for(bus.connect(), 10)
            async def interface(path, name):
                introspection = await asyncio.wait_for(bus.introspect("org.bluez", path), 10)
                return bus.get_proxy_object("org.bluez", path, introspection).get_interface(name)

            manager = await interface("/", "org.freedesktop.DBus.ObjectManager")
            objects = await asyncio.wait_for(manager.call_get_managed_objects(), 5)
            adapter_path = next((path for path, obj in objects.items() if "org.bluez.Adapter1" in obj), None)
            phone_path = next((path for path, obj in objects.items() if "org.bluez.Device1" in obj and plain(obj["org.bluez.Device1"]).get("Address", "").casefold() == address.casefold()), None)
            if not phone_path:
                raise BluetoothStatusError("Saved iPhone bond is missing from Bluetooth")
            properties = plain(objects[phone_path]["org.bluez.Device1"])
            if not all(properties.get(key) for key in ("Paired", "Bonded", "Trusted")):
                raise BluetoothStatusError("iPhone bond or trust was lost")
            device = await interface(phone_path, "org.bluez.Device1")
            device_props = await interface(phone_path, "org.freedesktop.DBus.Properties")
            if not properties.get("Connected"):
                if monotonic() - self.last_discovery >= 30:
                    self.last_discovery = monotonic()
                    if adapter_path:
                        self.status = "Looking for paired iPhone"
                        try:
                            adapter = await interface(adapter_path, "org.bluez.Adapter1")
                            await prefer_le_bearer(device_props, properties)
                            self.last_reconnect_at = datetime.now(UTC).isoformat()
                            self.reconnect_attempts += 1
                            scan_connected = await self._scan_phone(manager, adapter, phone_path, address, device)
                            objects = await asyncio.wait_for(manager.call_get_managed_objects(), 5)
                            properties = plain(objects.get(phone_path, {}).get('org.bluez.Device1', {}))
                            if scan_connected and not properties.get('Connected'):
                                raise BluetoothStatusError('iPhone link dropped after reconnect; Luma will retry automatically')
                        except BluetoothStatusError:
                            # No duplicate direct request after a failed scan
                            # Connect. The outer worker applies its retry delay.
                            raise
                        except Exception:
                            # Some controllers cannot scan while another radio
                            # operation is active. Still attempt the direct bond.
                            pass
                        objects = await asyncio.wait_for(manager.call_get_managed_objects(), 5)
                        properties = plain(objects.get(phone_path, {}).get("org.bluez.Device1", {}))
                if not all(properties.get(key) for key in ("Paired", "Bonded", "Trusted")):
                    raise BluetoothStatusError("iPhone bond or trust was lost")
            if not properties.get("Connected"):
                if self.service.settings.phone_address != address:
                    raise BluetoothStatusError("Selected iPhone changed before reconnect")
                await prefer_le_bearer(device_props, properties)
                self.status = "Reconnecting to paired iPhone"
                self.last_reconnect_at = datetime.now(UTC).isoformat()
                self.reconnect_attempts += 1
                await self._connect_phone(manager, device, phone_path, address)
            try:
                objects = await wait_for_trusted_connection(manager, phone_path)
            except BluetoothStatusError as exc:
                if str(exc) != "iPhone connected; waiting for Bluetooth services":
                    raise
                adapter = await interface(adapter_path, "org.bluez.Adapter1") if adapter_path else None
                await self.refresh_phone_services(manager, device, device_props, phone_path, adapter, address)
                objects = await wait_for_trusted_connection(manager, phone_path, timeout=20)
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
            try:
                objects,chars=await wait_for_ancs(manager,phone_path,initial=objects)
            except BluetoothStatusError as exc:
                if str(exc) != 'iPhone connected, but notification service is unavailable':
                    raise
                # A Classic-only connection can report ServicesResolved while
                # never exposing the LE-only ANCS GATT service. Repair that
                # case too, instead of waiting forever for a service absent
                # from the selected bearer.
                adapter = await interface(adapter_path, "org.bluez.Adapter1") if adapter_path else None
                await self.refresh_phone_services(manager, device, device_props, phone_path, adapter, address)
                objects = await wait_for_trusted_connection(manager, phone_path, timeout=20)
                objects,chars=await wait_for_ancs(manager,phone_path,initial=objects)
            source = await interface(chars[SOURCE], "org.bluez.GattCharacteristic1")
            has_details = self.profile_id == 'primary' and DATA in chars and CONTROL in chars
            data = await interface(chars[DATA], "org.bluez.GattCharacteristic1") if has_details else None
            control = await interface(chars[CONTROL], "org.bluez.GattCharacteristic1") if has_details else None
            source_props = await interface(chars[SOURCE], "org.freedesktop.DBus.Properties")
            data_props = await interface(chars[DATA], "org.freedesktop.DBus.Properties") if has_details else None
            phone_props = await interface(phone_path, "org.freedesktop.DBus.Properties")
            phone_props.on_properties_changed(self.remote_authorized.properties_changed)
            manager.on_interfaces_removed(self.remote_authorized.interfaces_removed)
            notices = asyncio.Queue(maxsize=64)
            fragments = asyncio.Queue(maxsize=64)

            def enqueue(queue, changed):
                if "Value" in changed:
                    if queue.full():
                        queue.get_nowait()
                    queue.put_nowait(bytes(changed["Value"].value))

            source_props.on_properties_changed(lambda name, changed, invalidated: enqueue(notices, changed))
            source_props.on_properties_changed(self.remote_authorized.source_properties_changed)
            if data_props:
                data_props.on_properties_changed(lambda name, changed, invalidated: enqueue(fragments, changed))
            # Never unlock on RSSI, an advertisement or a merely connected
            # device: Notification Source must authorize its subscription.
            has_details = await subscribe_ancs(source, data)
            self.remote_authorized.begin(address, phone_path, chars[SOURCE])
            self.status = "Authorized ANCS session" if has_details else "Authorized iPhone; notification details unavailable"
            while self.service.settings.phone_address == address and self.remote_authorized.generation:
                props = plain(await asyncio.wait_for(phone_props.call_get_all("org.bluez.Device1"), 5))
                if not trusted_link(props):
                    self.status = "iPhone Bluetooth link or services disconnected"
                    break
                # Confirm the ANCS service still exists; iOS may unpublish it.
                current = await asyncio.wait_for(manager.call_get_managed_objects(), 5)
                if chars[SOURCE] not in current:
                    self.status = "iPhone notification service disappeared"
                    break
                if plain(current[chars[SOURCE]].get('org.bluez.GattCharacteristic1', {})).get('Notifying') is not True:
                    self.status = "iPhone notification subscription ended"
                    break
                self.service.phone_seen()
                self.scene_authorized = (address, monotonic())
                self.remote_authorized.heartbeat(address)
                if self.coordinator:
                    self.coordinator.note_authorized(self.profile_id)
                try:
                    raw = await asyncio.wait_for(notices.get(), 5)
                except asyncio.TimeoutError:
                    continue
                try:
                    notice = parse_source(raw)
                    if notice.event == 2:
                        self.service.remove_notification(str(notice.uid))
                        continue
                    if not has_details:
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
            self.remote_authorized.clear()
            with suppress(Exception):
                bus.disconnect()


async def prefer_le_bearer(properties_interface, properties: dict) -> bool:
    """Ask dual-mode BlueZ to use LE for ANCS, only when it exposes this option."""
    if "PreferredBearer" not in properties or properties.get("PreferredBearer") == "le":
        return False
    from dbus_next import Variant
    try:
        await asyncio.wait_for(properties_interface.call_set(
            "org.bluez.Device1", "PreferredBearer", Variant("s", "le")), 5)
        return True
    except Exception:
        return False


async def recover_stalled_services(manager, device, properties_interface, phone_path: str,
                                   *, adapter=None, address_is_current=lambda: True,
                                   pause=asyncio.sleep) -> None:
    """At most once per cooldown, rebuild a stalled bonded LE GATT session.

    Disconnect is scoped to the saved phone, never removes its bond, and is
    followed by a fresh Connect only while that phone remains selected.
    """
    objects = await asyncio.wait_for(manager.call_get_managed_objects(), 5)
    props = plain(objects.get(phone_path, {}).get("org.bluez.Device1", {}))
    if not trusted_link(props) or not address_is_current():
        raise BluetoothStatusError("iPhone connection changed before service recovery")
    try:
        try:
            await asyncio.wait_for(device.call_disconnect(), 8)
        except Exception:
            # A phone-initiated disconnect may race the request. Continue only
            # if BlueZ confirms that the saved, still-bonded phone is down.
            objects = await asyncio.wait_for(manager.call_get_managed_objects(), 5)
            fresh = plain(objects.get(phone_path, {}).get("org.bluez.Device1", {}))
            if (fresh.get("Connected") is True or not address_is_current()
                    or not all(fresh.get(key) is True for key in ("Paired", "Bonded", "Trusted"))):
                raise BluetoothStatusError("iPhone Bluetooth link did not reset; Luma will retry later")
        for _ in range(10):
            await pause(0.5)
            objects = await asyncio.wait_for(manager.call_get_managed_objects(), 5)
            fresh = plain(objects.get(phone_path, {}).get("org.bluez.Device1", {}))
            if not address_is_current():
                raise BluetoothStatusError("Selected iPhone changed during service recovery")
            if not fresh.get("Connected"):
                break
            # The phone can reconnect before the polling interval observes a
            # down edge. Fresh ANCS is a useful outcome; the outer session
            # still must successfully subscribe before granting presence.
            if trusted_link(fresh) and SOURCE in ancs_characteristics(objects, phone_path):
                return
        else:
            raise BluetoothStatusError("iPhone Bluetooth link did not reset; Luma will retry later")
        if not all(fresh.get(key) is True for key in ("Paired", "Bonded", "Trusted")):
            raise BluetoothStatusError("iPhone bond or trust was lost")
        if not address_is_current():
            raise BluetoothStatusError("Selected iPhone changed during service recovery")
        await prefer_le_bearer(properties_interface, fresh)
        scan_connected = False
        if adapter is not None:
            try:
                # A fresh LE advertisement helps BlueZ choose the GATT bearer
                # when an iPhone also has a BR/EDR bond. Discovery is bounded
                # and belongs only to this D-Bus connection.
                scan_connected = await scan_for_paired_phone(manager, adapter, phone_path,
                                            phone_address=fresh.get('Address'), pause=pause,
                                            connect=lambda: connect_paired_phone(manager, device, phone_path,
                                                address_is_current=address_is_current),
                                            address_is_current=address_is_current)
            except BluetoothStatusError:
                raise
            except Exception:
                pass
        objects = await asyncio.wait_for(manager.call_get_managed_objects(), 5)
        fresh = plain(objects.get(phone_path, {}).get("org.bluez.Device1", {}))
        if not all(fresh.get(key) is True for key in ("Paired", "Bonded", "Trusted")):
            raise BluetoothStatusError("iPhone bond or trust was lost")
        if not address_is_current():
            raise BluetoothStatusError("Selected iPhone changed during service recovery")
        if not fresh.get("Connected"):
            if scan_connected:
                raise BluetoothStatusError('iPhone link dropped after reconnect; Luma will retry automatically')
            await connect_paired_phone(manager, device, phone_path,
                                      address_is_current=address_is_current)
    except BluetoothStatusError:
        raise
    except Exception as exc:
        raise BluetoothStatusError("iPhone Bluetooth service recovery failed; Luma will retry later") from exc
