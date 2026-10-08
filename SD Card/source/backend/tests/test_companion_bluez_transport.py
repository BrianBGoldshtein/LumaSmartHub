"""Actual private D-Bus signals, synthetic BlueZ. No radio/owner system bus.

This checks dbus-next callback registration and ObjectManager wire behavior,
not whether a physical iPhone grants ANCS or automatically reconnects.
"""
import asyncio
from contextlib import suppress
import select
import shutil
import subprocess
import sys

import pytest
from dbus_next.aio import MessageBus
from dbus_next import Message
from dbus_next.constants import PropertyAccess
from dbus_next.service import ServiceInterface, dbus_property, method

from luma.api import create_app
from luma.integrations.ancs import SERVICE, SOURCE

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith('linux') or not shutil.which('dbus-daemon'),
    reason='Private Linux dbus-daemon required; no system bus fallback',
)
PHONE='AA:BB:CC:DD:EE:FF'
DEVICE='/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF'
GATT=DEVICE+'/service0001'
CHAR=GATT+'/char0002'


class Device(ServiceInterface):
    def __init__(self):
        super().__init__('org.bluez.Device1')
        self.connected=True

    @dbus_property(access=PropertyAccess.READ)
    def Address(self) -> 's': return PHONE

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


class GattService(ServiceInterface):
    def __init__(self): super().__init__('org.bluez.GattService1')

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> 's': return SERVICE

    @dbus_property(access=PropertyAccess.READ)
    def Device(self) -> 'o': return DEVICE


class Source(ServiceInterface):
    def __init__(self):
        super().__init__('org.bluez.GattCharacteristic1')
        self.notifying=False

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> 's': return SOURCE

    @dbus_property(access=PropertyAccess.READ)
    def Service(self) -> 'o': return GATT

    @dbus_property(access=PropertyAccess.READ)
    def Notifying(self) -> 'b': return self.notifying

    @method()
    def StartNotify(self):
        self.notifying=True
        self.emit_properties_changed({'Notifying':True})


async def until(check,timeout=4):
    deadline=asyncio.get_running_loop().time()+timeout
    while not check():
        if asyncio.get_running_loop().time()>=deadline:
            raise AssertionError('Private D-Bus ANCS condition timed out')
        await asyncio.sleep(.01)


@pytest.mark.asyncio
@pytest.mark.parametrize('loss',['disconnect','subscription','subscription_silent','source_removed','device_removed'])
async def test_real_signal_transport_clears_remote_authorization(tmp_path,monkeypatch,loss):
    daemon=subprocess.Popen(['dbus-daemon','--session','--nofork','--print-address=1'],
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    bus=None;task=None
    try:
        assert select.select([daemon.stdout],[],[],3)[0], 'Private daemon did not start'
        address=daemon.stdout.readline().strip()
        assert address.startswith('unix:'), 'Must never connect to the owner system bus'
        monkeypatch.setenv('DBUS_SYSTEM_BUS_ADDRESS',address)
        bus=await MessageBus(bus_address=address).connect()
        await bus.request_name('org.bluez')
        # Export a root object so dbus-next advertises its standard built-in
        # ObjectManager (child objects alone do not advertise it at root).
        bus.export('/',ServiceInterface('org.bluez.Qualification'))
        device=Device();source=Source()
        bus.export(DEVICE,device);bus.export(GATT,GattService());bus.export(CHAR,source)
        app=create_app(data_dir=tmp_path)
        app.state.luma.update_settings({'phone_address':PHONE})
        runtime=app.state.bluetooth
        task=asyncio.create_task(runtime.session(PHONE))
        await until(lambda: runtime.companion_presence().authorized or task.done())
        if task.done(): await task
        assert runtime.companion_presence().authorized and source.notifying
        original=runtime.companion_presence().generation
        if loss=='disconnect':
            device.connected=False;device.emit_properties_changed({'Connected':False})
        elif loss=='subscription':
            source.notifying=False;source.emit_properties_changed({'Notifying':False})
        elif loss=='subscription_silent':source.notifying=False
        else:
            path,interface=(CHAR,'org.bluez.GattCharacteristic1') if loss=='source_removed' else (DEVICE,'org.bluez.Device1')
            bus.unexport(path)
            # BlueZ emits this from its root ObjectManager. dbus-next's
            # service helper emits unexport from the child path instead.
            await bus.send(Message.new_signal('/','org.freedesktop.DBus.ObjectManager',
                'InterfacesRemoved','oas',[path,[interface]]))
        # Observe the actual transported signal, not a direct callback call.
        await until(lambda: not runtime.companion_presence().authorized,timeout=7 if loss=='subscription_silent' else 1)
        assert original and runtime.companion_presence().generation==''
    finally:
        try:
            if task is not None:
                task.cancel()
                # Preserve the original failure while guaranteeing daemon
                # cleanup even if the session task already failed.
                with suppress(asyncio.CancelledError,Exception): await task
            if bus is not None:
                bus.disconnect()
                with suppress(Exception):await bus.wait_for_disconnect()
        finally:
            daemon.terminate()
            try:daemon.wait(timeout=3)
            except subprocess.TimeoutExpired:
                daemon.kill();daemon.wait(timeout=3)
