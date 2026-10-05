"""ANCS consumer peripheral advertising, independent of reconnect attempts.

iOS is the ANCS GATT server; Luma solicits that service, it does not advertise
it as a service it provides. Advertising never authorizes privacy or pairing.
"""
import asyncio
from contextlib import suppress
import sys

from dbus_next.constants import PropertyAccess
from dbus_next.service import ServiceInterface, dbus_property, method

from .integrations.ancs import SERVICE

PATH = '/com/luma/ancs_reconnect'
MANAGER = 'org.bluez.LEAdvertisingManager1'


class ANCSSolicitation(ServiceInterface):
    def __init__(self):
        super().__init__('org.bluez.LEAdvertisement1')
        self.released = False

    @dbus_property(access=PropertyAccess.READ)
    def Type(self) -> 's':
        return 'peripheral'

    @dbus_property(access=PropertyAccess.READ)
    def SolicitUUIDs(self) -> 'as':
        return [SERVICE]

    @dbus_property(access=PropertyAccess.READ)
    def LocalName(self) -> 's':
        return 'Luma'

    @method()
    def Release(self):
        self.released = True


def reconnect_adapter(objects: dict, address: str) -> str | None:
    """Only solicit while the selected trusted bond exists and is absent."""
    if not address:
        return None
    for obj in objects.values():
        device = obj.get('org.bluez.Device1', {})
        values = {key: value.value for key, value in device.items()}
        if values.get('Address', '').casefold() != address.casefold():
            continue
        if not all(values.get(key) is True for key in ('Paired', 'Bonded', 'Trusted')):
            return None
        if values.get('Connected') is True:
            return None
        adapter = values.get('Adapter')
        candidate = objects.get(adapter, {})
        powered = candidate.get('org.bluez.Adapter1', {}).get('Powered')
        if powered and powered.value is True and MANAGER in candidate:
            return adapter
    return None


class ANCSReconnectAdvertising:
    def __init__(self, selected_address):
        self.selected_address = selected_address
        self.status = 'Waiting for selected iPhone'

    async def run(self, *, pause=asyncio.sleep, connect=None):
        if sys.platform != 'linux':
            self.status = 'Requires Linux BlueZ'
            return
        if connect is None:
            from dbus_next import BusType
            from dbus_next.aio import MessageBus
            async def connect():
                return await MessageBus(bus_type=BusType.SYSTEM).connect()
        while True:
            if not self.selected_address():
                self.status = 'Waiting for selected iPhone'
                await pause(2)
                continue
            try:
                await self.session(connect, pause=pause)
            except Exception:
                # Never expose D-Bus exceptions (can contain phone addresses).
                self.status = 'Reconnect advertising unavailable; retrying'
                await pause(10)

    async def session(self, connect, *, pause=asyncio.sleep):
        bus = advertising = None
        exported = False
        advertisement = ANCSSolicitation()
        registered_adapter = None
        try:
            bus = await asyncio.wait_for(connect(), 10)
            async def interface(path, name):
                intro = await asyncio.wait_for(bus.introspect('org.bluez', path), 5)
                return bus.get_proxy_object('org.bluez', path, intro).get_interface(name)
            manager = await interface('/', 'org.freedesktop.DBus.ObjectManager')
            bus.export(PATH, advertisement)
            exported = True
            while self.selected_address():
                objects = await asyncio.wait_for(manager.call_get_managed_objects(), 5)
                wanted_adapter = reconnect_adapter(objects, self.selected_address())
                if advertising and (registered_adapter != wanted_adapter or advertisement.released):
                    if not advertisement.released:
                        await asyncio.wait_for(advertising.call_unregister_advertisement(PATH), 5)
                    advertising = registered_adapter = None
                    advertisement.released = False
                if wanted_adapter and advertising is None:
                    candidate = await interface(wanted_adapter, MANAGER)
                    await asyncio.wait_for(candidate.call_register_advertisement(PATH, {}), 5)
                    advertising = candidate
                    registered_adapter = wanted_adapter
                self.status = ('Advertising iPhone notification reconnect' if advertising else
                               'Phone linked, radio off, or selected bond unavailable')
                await pause(2)
        finally:
            # Cancellation, forget-phone and API shutdown all release the
            # advertisement. BlueZ also releases it if this bus disappears.
            if advertising and not advertisement.released:
                with suppress(Exception):
                    await asyncio.wait_for(advertising.call_unregister_advertisement(PATH), 5)
            if bus:
                if exported:
                    bus.unexport(PATH, advertisement)
                bus.disconnect()
            self.status = 'Waiting for selected iPhone'
