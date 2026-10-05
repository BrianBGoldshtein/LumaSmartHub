"""Real D-Bus cancellation checks; no claim of Pi controller/iOS acceptance."""
import asyncio
import os
import shutil
import signal
import subprocess
from types import SimpleNamespace

from dbus_next.constants import PropertyAccess
from dbus_next.service import ServiceInterface, dbus_property, method
import pytest

from luma.bluetooth_runtime import BluetoothStatusError, connect_paired_phone


class PendingPhone(ServiceInterface):
    def __init__(self):
        super().__init__('org.bluez.Device1')
        self.pending = asyncio.Event()
        self.stopped = asyncio.Event()
        self.disconnect_calls = 0

    @dbus_property(access=PropertyAccess.READ)
    def Paired(self) -> 'b':
        return True

    @dbus_property(access=PropertyAccess.READ)
    def Bonded(self) -> 'b':
        return True

    @dbus_property(access=PropertyAccess.READ)
    def Trusted(self) -> 'b':
        return True

    @dbus_property(access=PropertyAccess.READ)
    def Connected(self) -> 'b':
        return False

    @method()
    async def Connect(self):
        self.pending.set()
        await self.stopped.wait()

    @method()
    def Disconnect(self):
        self.disconnect_calls += 1
        self.stopped.set()


@pytest.mark.asyncio
async def test_timeout_reaches_pending_bluez_server_as_explicit_disconnect():
    if not shutil.which('dbus-daemon'):
        pytest.skip('private D-Bus transport requires dbus-daemon')
    from dbus_next.aio import MessageBus
    result = subprocess.run(['dbus-daemon', '--session', '--fork', '--print-address=1',
                             '--print-pid=1'], capture_output=True, text=True, check=True, timeout=5)
    address, pid = result.stdout.strip().splitlines()
    owner = client = None
    phone = PendingPhone()
    try:
        owner = await MessageBus(bus_address=address).connect()
        client = await MessageBus(bus_address=address).connect()
        owner.export('/phone', phone)
        intro = await client.introspect(owner.unique_name, '/phone')
        proxy = client.get_proxy_object(owner.unique_name, '/phone', intro)
        device = proxy.get_interface('org.bluez.Device1')
        properties = proxy.get_interface('org.freedesktop.DBus.Properties')
        async def snapshot():
            return {'/phone': {'org.bluez.Device1': await properties.call_get_all('org.bluez.Device1')}}
        manager = SimpleNamespace(call_get_managed_objects=snapshot)
        with pytest.raises(BluetoothStatusError, match='did not finish'):
            await connect_paired_phone(manager, device, '/phone', timeout=.05)
        assert phone.pending.is_set() and phone.stopped.is_set()
        assert phone.disconnect_calls == 1
        current = await properties.call_get_all('org.bluez.Device1')
        assert all(current[key].value for key in ('Paired','Bonded','Trusted'))
    finally:
        phone.stopped.set()
        if client:
            client.disconnect()
            await client.wait_for_disconnect()
        if owner:
            owner.disconnect()
            await owner.wait_for_disconnect()
        os.kill(int(pid), signal.SIGTERM)
