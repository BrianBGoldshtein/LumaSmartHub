"""Read-only BlueZ signals wake verifiers; they never grant phone presence."""
import asyncio
from contextlib import suppress

from dbus_next import BusType, Message, MessageType
from dbus_next.aio import MessageBus

from .integrations.ancs import SERVICE, SOURCE

DEVICE = 'org.bluez.Device1'
GATT = 'org.bluez.GattService1'
CHAR = 'org.bluez.GattCharacteristic1'
FIELDS = {DEVICE:{'Address','Connected','ServicesResolved','Paired','Bonded','Trusted','Blocked'},
          GATT:{'Device','UUID'}, CHAR:{'Service','UUID','Notifying'}}


def slim(properties):
    return {key:getattr(value,'value',value) for key,value in properties.items()}


class PhoneSignalMonitor:
    def __init__(self, notify, reset):
        self.notify, self.reset = notify, reset
        self.objects = {}
        self.owner = ''

    def remember(self, path, interfaces):
        target = self.objects.setdefault(path,{})
        for name,properties in interfaces.items():
            if name in FIELDS:
                target[name] = {key:value for key,value in slim(properties).items() if key in FIELDS[name]}

    def address(self, path):
        obj = self.objects.get(path,{})
        if DEVICE in obj:
            return obj[DEVICE].get('Address')
        if GATT in obj:
            return self.address(obj[GATT].get('Device'))
        if CHAR in obj:
            return self.address(obj[CHAR].get('Service'))
        return None

    def ancs(self, path):
        obj = self.objects.get(path,{})
        return (obj.get(CHAR,{}).get('UUID','').lower()==SOURCE
                or obj.get(GATT,{}).get('UUID','').lower()==SERVICE)

    def handle(self, message):
        # A unicast forged signal must not bypass the daemon's AddMatch rule.
        if message.message_type!=MessageType.SIGNAL or message.sender!=self.owner:
            return
        path = message.path
        body = message.body
        if (message.interface,message.member)==('org.freedesktop.DBus.Properties','PropertiesChanged') and len(body)==3:
            name,changed,invalidated = body
            if name not in FIELDS or not isinstance(changed,dict) or not isinstance(invalidated,list):
                return
            address = self.address(path)
            before_ancs = self.ancs(path)
            values = {key:value for key,value in slim(changed).items() if key in FIELDS[name]}
            self.objects.setdefault(path,{}).setdefault(name,{}).update(values)
            if address and name==DEVICE:
                self.notify(address,'device',values,invalidated,False)
            elif address and before_ancs and ('Notifying' in values or 'Notifying' in invalidated):
                self.notify(address,'ancs',values,invalidated,False)
        elif message.interface=='org.freedesktop.DBus.ObjectManager':
            if message.member=='InterfacesAdded' and len(body)==2:
                added,interfaces=body
                self.remember(added,interfaces)
                address=self.address(added)
                if address and DEVICE in interfaces:
                    self.notify(address,'device',self.objects[added][DEVICE],[],False)
                elif address and self.ancs(added):
                    self.notify(address,'ancs',{},[],False)
            elif message.member=='InterfacesRemoved' and len(body)==2:
                removed,interfaces=body
                address=self.address(removed)
                kind='device' if DEVICE in interfaces else 'ancs' if self.ancs(removed) else None
                if address and kind:
                    self.notify(address,kind,{},[],True)
                for name in interfaces:
                    self.objects.get(removed,{}).pop(name,None)

    async def session(self):
        bus = await asyncio.wait_for(MessageBus(bus_type=BusType.SYSTEM).connect(),10)
        tasks=[]
        try:
            intro=await asyncio.wait_for(bus.introspect('org.freedesktop.DBus','/org/freedesktop/DBus'),5)
            daemon=bus.get_proxy_object('org.freedesktop.DBus','/org/freedesktop/DBus',intro).get_interface('org.freedesktop.DBus')
            self.owner=await asyncio.wait_for(daemon.call_get_name_owner('org.bluez'),5)
            changed=asyncio.Event()
            def owner_changed(name,old,new):
                if name=='org.bluez' and old!=new:
                    self.reset()
                    changed.set()
            daemon.on_name_owner_changed(owner_changed)
            bus.add_message_handler(self.handle)
            for interface in ('org.freedesktop.DBus.Properties','org.freedesktop.DBus.ObjectManager'):
                reply=await asyncio.wait_for(bus.call(Message(destination='org.freedesktop.DBus',
                    path='/org/freedesktop/DBus',interface='org.freedesktop.DBus',member='AddMatch',
                    signature='s',body=[f"type='signal',sender='org.bluez',interface='{interface}'"])),5)
                if reply.message_type==MessageType.ERROR:
                    raise RuntimeError('Bluetooth signal subscription unavailable')
            intro=await asyncio.wait_for(bus.introspect('org.bluez','/'),5)
            manager=bus.get_proxy_object('org.bluez','/',intro).get_interface('org.freedesktop.DBus.ObjectManager')
            snapshot=await asyncio.wait_for(manager.call_get_managed_objects(),5)
            if await asyncio.wait_for(daemon.call_get_name_owner('org.bluez'),5)!=self.owner:
                # Close the owner-change race between the first lookup and
                # installing its signal handler. Never retain old-daemon hints.
                self.reset()
                return
            self.objects={}
            for path,interfaces in snapshot.items():
                self.remember(path,interfaces)
            # Wake an already-linked phone at monitor startup too. Verifiers
            # re-read its bond/GATT consent before exposing any private data.
            for obj in self.objects.values():
                props=obj.get(DEVICE,{})
                if props.get('Address') and props.get('Connected') is True:
                    self.notify(props['Address'],'device',props,[],False)
            tasks=[asyncio.create_task(changed.wait()),asyncio.create_task(bus.wait_for_disconnect())]
            await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks: task.cancel()
            if tasks: await asyncio.gather(*tasks,return_exceptions=True)
            with suppress(Exception): bus.disconnect()
            self.owner=''

    async def run(self):
        while True:
            try:
                await self.session()
            except Exception:
                # A failed observer must not invalidate a separate healthy
                # verifier. Actual BlueZ owner loss is handled above.
                pass
            await asyncio.sleep(1)
