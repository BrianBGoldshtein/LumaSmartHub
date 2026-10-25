"""Real private-bus radio noise must not starve the production health route."""
import asyncio
from contextlib import suppress
import select
import shutil
import subprocess
import sys
import time

import httpx
import pytest
from dbus_next import Message,MessageType,Variant
from dbus_next.aio import MessageBus
from dbus_next.constants import PropertyAccess
from dbus_next.service import ServiceInterface, dbus_property

from luma.api import create_app
from luma import bluetooth_runtime
from test_multi_bluetooth import ADAPTER, Adapter, Device, until

pytestmark=pytest.mark.skipif(not sys.platform.startswith('linux') or not shutil.which('dbus-daemon'),
    reason='Private Linux D-Bus required; no system-bus fallback')


class RadioDevice(Device):
    @dbus_property(access=PropertyAccess.READ)
    def RSSI(self)->'n': return -60


@pytest.mark.asyncio
async def test_unrelated_radio_flood_keeps_health_live_and_shutdown_bounded(tmp_path,monkeypatch):
    daemon=subprocess.Popen(['dbus-daemon','--session','--nofork','--print-address=1'],
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    bus=worker=None
    processed=lookups=0
    try:
        assert select.select([daemon.stdout],[],[],3)[0]
        address=daemon.stdout.readline().strip()
        assert address.startswith('unix:')
        monkeypatch.setenv('DBUS_SYSTEM_BUS_ADDRESS',address)
        bus=await MessageBus(bus_address=address).connect()
        await bus.request_name('org.bluez')
        bus.export('/',ServiceInterface('org.bluez.LoadQualification'))
        bus.export(ADAPTER,Adapter())
        phone='AA:BB:CC:DD:EE:01'
        selected=ADAPTER+'/dev_'+phone.replace(':','_')
        bus.export(selected,Device(phone,fail=True))  # Registered phone is absent.
        radios=[]
        for i in range(40):
            other=f'AA:BB:CC:DD:EF:{i:02X}'
            radio=RadioDevice(other)
            bus.export(ADAPTER+'/dev_'+other.replace(':','_'),radio)
            radios.append(radio)
        app=create_app(data_dir=tmp_path)
        app.state.luma.update_settings({'phone_address':phone})
        runtime=app.state.bluetooth
        receive=runtime.signals.handle
        def observed(message):
            nonlocal processed
            receive(message)
            if (message.message_type==MessageType.SIGNAL and
                message.interface=='org.freedesktop.DBus.Properties' and
                message.member=='PropertiesChanged' and len(message.body)==3 and
                ('RSSI' in message.body[1] or 'Trusted' in message.body[1])):
                processed+=1
        runtime.signals.handle=observed
        lookup=app.state.profiles.by_phone
        def slow_lookup(value):
            nonlocal lookups
            lookups+=1
            time.sleep(.001)  # Model even a modest SD-backed lookup cost.
            return lookup(value)
        monkeypatch.setattr(app.state.profiles,'by_phone',slow_lookup)
        scan=bluetooth_runtime.scan_for_paired_phone
        async def brief_scan(*args,**kwargs):
            kwargs['pause']=lambda _:asyncio.sleep(0)
            return await scan(*args,**kwargs)
        monkeypatch.setattr(bluetooth_runtime,'scan_for_paired_phone',brief_scan)
        worker=asyncio.create_task(runtime.run())
        await until(lambda:runtime.signals.owner and len(runtime.signals.objects)>=42)
        assert runtime.present_ids()==set()
        delays=[]
        finished=asyncio.Event()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8742') as client:
            async def probe():
                scheduled=asyncio.get_running_loop().time()
                while not finished.is_set() or len(delays)<30:
                    response=await client.get('/api/v1/health')
                    # Include time the event loop could not even schedule the
                    # request, rather than hiding starvation before client.get.
                    delays.append(asyncio.get_running_loop().time()-scheduled)
                    assert response.status_code==200 and response.json()['database']=='ok'
                    scheduled=asyncio.get_running_loop().time()+.01
                    await asyncio.sleep(.01)
            checking=asyncio.create_task(probe())
            try:
                for i in range(4000):
                    # Both irrelevant RSSI and relevant-but-unregistered link
                    # hints are common while discovering nearby devices.
                    radio=radios[i%len(radios)]
                    # Await the producer's send completion: dbus-next's fake
                    # server writer otherwise drops messages on socket EAGAIN.
                    # This is still a real bus stream, not direct callbacks.
                    await bus.send(Message.new_signal(
                        ADAPTER+'/dev_'+radio.address.replace(':','_'),
                        'org.freedesktop.DBus.Properties','PropertiesChanged','sa{sv}as',
                        ['org.bluez.Device1',{'RSSI':Variant('n',-60)} if i%2 else
                            {'Trusted':Variant('b',True)},[]]))
                await until(lambda:processed>=4000,timeout=10)
                finished.set()
                await asyncio.wait_for(checking,5)
            finally:
                finished.set()
                checking.cancel()
                await asyncio.gather(checking,return_exceptions=True)
        assert lookups==0
        assert max(delays)<2  # Keep the installer's existing two-second request budget.
        assert runtime.present_ids()==set()
        stop_started=asyncio.get_running_loop().time()
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(worker,2)
        print(f'Radio qualification: signals={processed}; profile_lookups={lookups}; '
              f'health_probes={len(delays)}; max_health_seconds={max(delays):.4f}; '
              f'shutdown_seconds={asyncio.get_running_loop().time()-stop_started:.4f}')
    finally:
        if worker:
            worker.cancel()
            with suppress(asyncio.CancelledError): await worker
        if bus: bus.disconnect()
        daemon.terminate()
        try: daemon.wait(timeout=3)
        except subprocess.TimeoutExpired: daemon.kill();daemon.wait(timeout=3)
        if daemon.stdout: daemon.stdout.close()
