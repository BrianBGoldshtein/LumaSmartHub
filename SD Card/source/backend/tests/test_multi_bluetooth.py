"""Five actual D-Bus clients against synthetic BlueZ, never the owner's radio."""
import asyncio
from contextlib import suppress
import select
import shutil
import subprocess
import sys

import pytest
from dbus_next.aio import MessageBus
from dbus_next.errors import DBusError
from dbus_next.constants import PropertyAccess
from dbus_next.service import ServiceInterface, dbus_property, method

from luma import bluetooth_runtime
from luma.integrations.ancs import SERVICE, SOURCE
from luma.multi_bluetooth import MultiPhoneBluetooth
from luma.profiles import ProfileRepository
from luma.service import LumaService
from luma.storage import Storage

pytestmark = pytest.mark.skipif(not sys.platform.startswith('linux') or not shutil.which('dbus-daemon'),
                               reason='Private Linux D-Bus required; no system bus fallback')
ADAPTER = '/org/bluez/hci0'


class Adapter(ServiceInterface):
    def __init__(self):
        super().__init__('org.bluez.Adapter1')
        self.scans = 0
        self.filters = []

    @dbus_property(access=PropertyAccess.READ)
    def Powered(self) -> 'b': return True

    @method()
    def SetDiscoveryFilter(self, filters: 'a{sv}'):
        self.filters.append(filters)

    @method()
    def StartDiscovery(self): self.scans += 1

    @method()
    def StopDiscovery(self): pass


class Device(ServiceInterface):
    def __init__(self, address, *, fail=False):
        super().__init__('org.bluez.Device1')
        self.address, self.fail = address, fail
        self.connected = False
        self.connects = 0
        self.disconnects = 0

    @dbus_property(access=PropertyAccess.READ)
    def Address(self) -> 's': return self.address

    @dbus_property(access=PropertyAccess.READ)
    def Adapter(self) -> 'o': return ADAPTER

    @dbus_property(access=PropertyAccess.READ)
    def Paired(self) -> 'b': return True

    @dbus_property(access=PropertyAccess.READ)
    def Bonded(self) -> 'b': return True

    @dbus_property(access=PropertyAccess.READ)
    def Trusted(self) -> 'b': return True

    @dbus_property(access=PropertyAccess.READ)
    def Connected(self) -> 'b': return self.connected

    @dbus_property(access=PropertyAccess.READ)
    def ServicesResolved(self) -> 'b': return True

    @method()
    def Connect(self):
        self.connects += 1
        if self.fail:
            raise DBusError('org.bluez.Error.Failed', 'Synthetic link failure')
        self.set_connected(True)

    @method()
    def Disconnect(self):
        self.disconnects += 1
        self.set_connected(False)

    def set_connected(self, value):
        self.connected = value
        self.emit_properties_changed({'Connected': value})


class Gatt(ServiceInterface):
    def __init__(self, device):
        super().__init__('org.bluez.GattService1')
        self.device = device

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> 's': return SERVICE

    @dbus_property(access=PropertyAccess.READ)
    def Device(self) -> 'o': return self.device


class Source(ServiceInterface):
    def __init__(self, service):
        super().__init__('org.bluez.GattCharacteristic1')
        self.service = service
        self.notifying = False

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> 's': return SOURCE

    @dbus_property(access=PropertyAccess.READ)
    def Service(self) -> 'o': return self.service

    @dbus_property(access=PropertyAccess.READ)
    def Notifying(self) -> 'b': return self.notifying

    @method()
    def StartNotify(self):
        self.notifying = True
        self.emit_properties_changed({'Notifying': True})


async def until(check, timeout=5):
    deadline = asyncio.get_running_loop().time() + timeout
    while not check():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError('Synthetic multi-phone condition timed out')
        await asyncio.sleep(.01)


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['none', 'one_link', 'one_subscription', 'one_removed'])
async def test_five_real_sessions_reconnect_and_isolate_failures(tmp_path, monkeypatch, failure):
    daemon = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--print-address=1'],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    bus = task = None
    try:
        assert select.select([daemon.stdout], [], [], 3)[0]
        address = daemon.stdout.readline().strip()
        assert address.startswith('unix:')
        monkeypatch.setenv('DBUS_SYSTEM_BUS_ADDRESS', address)
        bus = await MessageBus(bus_address=address).connect()
        await bus.request_name('org.bluez')
        bus.export('/', ServiceInterface('org.bluez.Qualification'))
        adapter = Adapter()
        bus.export(ADAPTER, adapter)
        storage = Storage(tmp_path/'luma.db')
        profiles = ProfileRepository(storage)
        users = [profiles.get('primary')] + [profiles.create_secondary(f'Guest {i}') for i in range(4)]
        devices, sources, paths = [], [], []
        for index, user in enumerate(users):
            phone = f'AA:BB:CC:DD:EE:{index+1:02X}'
            profiles.bind_phone(user.id, phone)
            path = ADAPTER+'/dev_'+phone.replace(':', '_')
            gatt, char = path+'/service0001', path+'/service0001/char0002'
            device = Device(phone, fail=failure == 'one_link' and index == 4)
            source = Source(gatt)
            bus.export(path, device); bus.export(gatt, Gatt(path)); bus.export(char, source)
            devices.append(device); sources.append(source); paths.append(path)
        # Exercise the real scan + Device1.Connect wire calls, but accelerate
        # only its 0.5-second observation pauses in this disposable fixture.
        original_scan = bluetooth_runtime.scan_for_paired_phone
        async def scan(*args, **kwargs):
            kwargs['pause'] = lambda _: asyncio.sleep(0)
            return await original_scan(*args, **kwargs)
        monkeypatch.setattr(bluetooth_runtime, 'scan_for_paired_phone', scan)
        service = LumaService(storage)
        runtime = MultiPhoneBluetooth(service, profiles)
        task = asyncio.create_task(runtime.run())
        expected = {user.id for user in users[:4] if failure == 'one_link'} if failure == 'one_link' else {user.id for user in users}
        await until(lambda: runtime.present_ids() == expected)
        assert adapter.scans == 1
        assert all('Pattern' not in value for value in adapter.filters)
        assert all(device.connects == 1 for device in devices)
        assert all(device.disconnects == 0 for device in devices)
        generations = {uid: runtime.companion_presence(uid).generation for uid in expected}
        if failure in {'one_subscription', 'one_removed'}:
            lost = users[-1].id
            if failure == 'one_subscription':
                sources[-1].notifying = False
                sources[-1].emit_properties_changed({'Notifying': False})
            else:
                bus.unexport(paths[-1])
            await until(lambda: not runtime.companion_presence(lost).authorized)
            assert runtime.present_ids() == expected - {lost}
            assert all(runtime.companion_presence(uid).generation == generation for uid, generation in generations.items() if uid != lost)
        if failure == 'none':
            # Lost primary never locks out a guest, and no other device gets
            # Disconnect as a side effect of its property loss.
            devices[0].set_connected(False)
            await until(lambda: not runtime.companion_presence('primary').authorized)
            assert len(runtime.present_ids()) == 4
            assert all(device.disconnects == 0 for device in devices)
            devices[0].set_connected(True)  # incoming/manual return, still not ANCS proof
            assert not runtime.companion_presence('primary').authorized
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError): await task
        if bus: bus.disconnect()
        daemon.terminate()
        try: daemon.wait(timeout=3)
        except subprocess.TimeoutExpired:
            daemon.kill(); daemon.wait(timeout=3)
        if daemon.stdout: daemon.stdout.close()
