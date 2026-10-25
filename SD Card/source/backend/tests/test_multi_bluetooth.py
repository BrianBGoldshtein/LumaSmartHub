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
from luma.integrations.ancs import SERVICE, SOURCE, DATA, CONTROL
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
        self.resolved = True
        self.blocked = False

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
    def ServicesResolved(self) -> 'b': return self.resolved

    @dbus_property(access=PropertyAccess.READ)
    def Blocked(self) -> 'b': return self.blocked

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


class PendingDevice(Device):
    def __init__(self,address,gate):
        super().__init__(address)
        self.gate=gate

    @method()
    async def Connect(self):
        self.connects+=1
        await self.gate.wait()
        self.set_connected(True)


class Source(ServiceInterface):
    def __init__(self, service, *, uuid=SOURCE, gate=None, deny=False):
        super().__init__('org.bluez.GattCharacteristic1')
        self.service = service
        self.notifying = False
        self.subscriptions = 0
        self.uuid,self.gate,self.deny=uuid,gate,deny

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> 's': return self.uuid

    @dbus_property(access=PropertyAccess.READ)
    def Service(self) -> 'o': return self.service

    @dbus_property(access=PropertyAccess.READ)
    def Notifying(self) -> 'b': return self.notifying

    @method()
    def StartNotify(self):
        self.subscriptions += 1
        if self.deny:
            raise DBusError('org.bluez.Error.NotAuthorized','Synthetic permission denial')
        self.notifying = True
        self.emit_properties_changed({'Notifying': True})


class SlowSource(Source):
    @method()
    async def StartNotify(self):
        self.subscriptions+=1
        await self.gate.wait()
        self.notifying=True
        self.emit_properties_changed({'Notifying':True})


async def until(check, timeout=5):
    deadline = asyncio.get_running_loop().time() + timeout
    while not check():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError('Synthetic multi-phone condition timed out')
        await asyncio.sleep(.01)


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['none', 'one_link', 'primary_subscription', 'one_removed', 'no_secondary_ancs', 'secondary_subscription', 'secondary_blocked', 'secondary_unresolved', 'secondary_disconnect', 'late_primary','late_secondary','slow_optional','slow_optional_discovery','denied_primary','bluez_restart','queued_primary','queued_secondary','pending_connect'])
async def test_five_real_sessions_reconnect_and_isolate_failures(tmp_path, monkeypatch, failure):
    daemon = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--print-address=1'],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    bus = task = None
    data_gate=asyncio.Event()
    connect_gate=asyncio.Event()
    discovery_started=asyncio.Event()
    held_lock=None
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
            device = Device(phone, fail=(failure in {'one_link','late_secondary'} and index == 4)
                or (failure=='late_primary' and index==0))
            if failure=='pending_connect' and index==0:
                device=PendingDevice(phone,connect_gate)
            source = Source(gatt,deny=failure=='denied_primary' and index==0)
            bus.export(path, device)
            if index == 0 or failure != 'no_secondary_ancs':
                bus.export(gatt, Gatt(path)); bus.export(char, source)
            devices.append(device); sources.append(source); paths.append(path)
            if failure in {'slow_optional','slow_optional_discovery'} and index==0:
                data_source=SlowSource(gatt,uuid=DATA,gate=data_gate)
                bus.export(gatt+'/char0003',data_source)
                bus.export(gatt+'/char0004',Source(gatt,uuid=CONTROL))
                if failure=='slow_optional_discovery':
                    original_introspect=MessageBus.introspect
                    async def slow_introspect(client,bus_name,object_path,*args,**kwargs):
                        if object_path==paths[0]+'/service0001/char0003':
                            discovery_started.set()
                            await data_gate.wait()
                        return await original_introspect(client,bus_name,object_path,*args,**kwargs)
                    monkeypatch.setattr(MessageBus,'introspect',slow_introspect)
        # Exercise the real scan + Device1.Connect wire calls, but accelerate
        # only its 0.5-second observation pauses in this disposable fixture.
        original_scan = bluetooth_runtime.scan_for_paired_phone
        async def scan(*args, **kwargs):
            kwargs['pause'] = lambda _: asyncio.sleep(0)
            return await original_scan(*args, **kwargs)
        monkeypatch.setattr(bluetooth_runtime, 'scan_for_paired_phone', scan)
        service = LumaService(storage)
        runtime = MultiPhoneBluetooth(service, profiles)
        backoff=[]
        if failure in {'late_primary','late_secondary'}:
            def long_backoff(uid):
                backoff.append(uid)
                return 120
            runtime.coordinator.failure_delay=long_backoff
        if failure in {'queued_primary','queued_secondary'}:
            held_lock=runtime.coordinator._locks.setdefault('hci0',asyncio.Lock())
            await held_lock.acquire()
        task = asyncio.create_task(runtime.run())
        if held_lock is not None:
            index=0 if failure=='queued_primary' else 4
            incoming=users[index].id
            await until(lambda:incoming in runtime.coordinator._pending)
            devices[index].set_connected(True)
            await until(lambda:runtime.companion_presence(incoming).authorized,timeout=2)
            assert held_lock.locked() and all(device.disconnects==0 for device in devices)
            held_lock.release();held_lock=None
        if failure=='pending_connect':
            await until(lambda:devices[0].connects==1)
            devices[0].set_connected(True)
            await until(lambda:runtime.companion_presence('primary').authorized,timeout=2)
            assert not connect_gate.is_set() and devices[0].disconnects==0
            connect_gate.set()
        absent=users[0].id if failure in {'late_primary','denied_primary'} else users[-1].id if failure in {'one_link','late_secondary'} else None
        expected = {user.id for user in users if user.id!=absent}
        await until(lambda: runtime.present_ids() == expected)
        assert adapter.scans == 1
        assert all('Pattern' not in value for value in adapter.filters)
        assert all(device.connects == (0 if failure=='queued_primary' and i==0
            or failure=='queued_secondary' and i==4 else 1) for i,device in enumerate(devices))
        assert all(device.disconnects == 0 for device in devices)
        assert sources[0].subscriptions == (0 if failure=='late_primary' else 1)
        assert all(source.subscriptions == 0 for source in sources[1:])
        assert runtime.notification_addresses() == (users[0].phone_address or 'AA:BB:CC:DD:EE:01',)
        generations = {uid: runtime.companion_presence(uid).generation for uid in expected}
        if failure in {'late_primary','late_secondary'}:
            await until(lambda:absent in backoff)
            index=0 if failure=='late_primary' else 4
            devices[index].fail=False
            start=asyncio.get_running_loop().time()
            devices[index].set_connected(True)  # Incoming/manual link during 120-second retry wait.
            await until(lambda:runtime.companion_presence(absent).authorized,timeout=2)
            assert asyncio.get_running_loop().time()-start<2
            assert runtime.present_ids()=={user.id for user in users}
            assert all(runtime.companion_presence(uid).generation==generation for uid,generation in generations.items())
            assert all(device.disconnects==0 for device in devices)
        if failure=='slow_optional':
            await until(lambda:data_source.subscriptions==1)
            assert not data_gate.is_set() and runtime.companion_presence('primary').authorized
            assert service.state.phone_connected
            data_gate.set()
            await until(lambda:runtime.status=='Authorized ANCS session')
        if failure=='slow_optional_discovery':
            await until(discovery_started.is_set)
            assert not data_gate.is_set() and runtime.companion_presence('primary').authorized
            assert service.state.phone_connected and data_source.subscriptions==0
            data_gate.set()
            await until(lambda:runtime.status=='Authorized ANCS session')
        if failure=='denied_primary':
            assert not runtime.companion_presence('primary').authorized
        if failure=='bluez_restart':
            await bus.release_name('org.bluez')
            await until(lambda:not runtime.present_ids(),timeout=2)
            await bus.request_name('org.bluez')
            await until(lambda:runtime.present_ids()==expected,timeout=3)
            assert all(runtime.companion_presence(uid).generation!=generation for uid,generation in generations.items())
            assert all(device.disconnects==0 for device in devices)
        if failure in {'secondary_blocked', 'secondary_unresolved', 'secondary_disconnect'}:
            lost = users[-1].id
            if failure == 'secondary_blocked':
                devices[-1].blocked = True
                devices[-1].emit_properties_changed({'Blocked': True})
            elif failure == 'secondary_unresolved':
                devices[-1].resolved = False
                devices[-1].emit_properties_changed({'ServicesResolved': False})
            else:
                devices[-1].set_connected(False)
            await until(lambda: not runtime.companion_presence(lost).authorized)
            assert runtime.present_ids() == expected - {lost}
            assert all(runtime.companion_presence(uid).generation == generation for uid, generation in generations.items() if uid != lost)
            assert all(device.disconnects == 0 for device in devices[:-1])
        if failure == 'secondary_subscription':
            sources[-1].emit_properties_changed({'Notifying': False})
            await asyncio.sleep(.1)
            assert runtime.present_ids() == expected
        if failure in {'primary_subscription', 'one_removed'}:
            lost = users[0].id if failure == 'primary_subscription' else users[-1].id
            if failure == 'primary_subscription':
                sources[0].deny = True  # Authorization was revoked, not merely a transient callback.
                sources[0].notifying = False
                sources[0].emit_properties_changed({'Notifying': False})
            else:
                bus.unexport(paths[-1])
            await until(lambda: not runtime.companion_presence(lost).authorized)
            assert runtime.present_ids() == expected - {lost}
            assert all(runtime.companion_presence(uid).generation == generation for uid, generation in generations.items() if uid != lost)
        if failure == 'none':
            # Lost primary never locks out a guest, and no other device gets
            # Disconnect as a side effect of its property loss.
            devices[0].fail = True  # Phone is actually out of range until the incoming return below.
            devices[0].set_connected(False)
            await until(lambda: not runtime.companion_presence('primary').authorized)
            assert len(runtime.present_ids()) == 4
            assert all(device.disconnects == 0 for device in devices)
            devices[0].set_connected(True)  # incoming/manual return, still not ANCS proof
            assert not runtime.companion_presence('primary').authorized
    finally:
        data_gate.set()
        connect_gate.set()
        if held_lock is not None and held_lock.locked():
            held_lock.release()
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError): await task
        if bus: bus.disconnect()
        daemon.terminate()
        try: daemon.wait(timeout=3)
        except subprocess.TimeoutExpired:
            daemon.kill(); daemon.wait(timeout=3)
        if daemon.stdout: daemon.stdout.close()


def test_secondary_notification_delivery_is_rejected_even_if_called_accidentally(tmp_path):
    storage = Storage(tmp_path/'luma.db')
    profiles = ProfileRepository(storage)
    user = profiles.create_secondary('Alex')
    profiles.bind_phone(user.id, 'AA:BB:CC:DD:EE:02')
    service = LumaService(storage)
    runtime = MultiPhoneBluetooth(service, profiles)
    child = runtime.runtime(user.id)
    from unittest.mock import Mock
    service.receive_notification = Mock()
    assert child.service.receive_notification(object()) is False
    service.receive_notification.assert_not_called()
