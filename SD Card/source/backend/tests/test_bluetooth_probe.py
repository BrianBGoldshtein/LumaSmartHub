"""Passive diagnostic privacy and genuine private-D-Bus monitoring checks."""
import asyncio
import importlib.util
import os
from pathlib import Path
import shutil
import signal
import subprocess

from dbus_next import DBusError, Message, MessageType
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method
import pytest

spec = importlib.util.spec_from_file_location('bluetooth_probe',
    Path(__file__).resolve().parents[2] / 'tools' / 'probe-bluetooth-reconnect.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.mark.parametrize('name,body,expected', [
    ('org.bluez.Error.InProgress', ['private phone name'], 'InProgress'),
    ('org.bluez.Error.Failed', ['le-connection-abort-by-local'], 'Failed: le-connection-abort-by-local'),
    ('org.bluez.Error.Failed', ['le-connection-key-missing'], 'Failed: le-connection-key-missing'),
    ('org.bluez.Error.Failed', ['br-connection-canceled'], 'Failed: br-connection-canceled'),
    ('org.bluez.Error.Failed', ['le-connection-address-secret'], 'Failed'),
    ('private.error.name', ['private key'], 'Other error'),
])
def test_probe_outputs_only_allowlisted_failure_labels(name, body, expected):
    message = Message(message_type=MessageType.ERROR, error_name=name, reply_serial=1,
                      signature='s', body=body)
    assert probe.error_label(message) == expected


def test_shell_fallback_redacts_identifiers_and_unknown_body_text():
    if not shutil.which('bash') or not shutil.which('sed'):
        pytest.skip('Linux shell filter unavailable')
    script = Path(__file__).resolve().parents[2] / 'tools' / 'probe-bluetooth-reconnect-errors.sh'
    sample = '''method call time=1791400000.000001 sender=:1.29 -> destination=org.bluez serial=50 path=/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF; interface=org.bluez.Device1; member=Connect
error time=1791400015.000001 sender=:1.10 -> destination=:1.29 error_name=org.bluez.Error.Failed reply_serial=50
   string "le-connection-abort-by-local"
   string "private phone name AA:BB:CC:DD:EE:FF"
   string "le-connection-private-token"
method call time=1791400015.000002 sender=:1.29 -> destination=org.bluez serial=51 path=/private; interface=org.bluez.Device1; member=Disconnect
error time=1791400016.000001 sender=:1.10 -> destination=:1.29 error_name=org.bluez.Error.InProgress reply_serial=52
error time=1791400016.000002 sender=:1.10 -> destination=:1.29 error_name=org.bluez.Error.FailedPrivateName reply_serial=53
'''
    result = subprocess.run(['bash', str(script), '--filter-only'], input=sample,
                            capture_output=True, text=True, check=True, timeout=5)
    assert result.stdout.splitlines() == [
        '1791400000.000001 Connect', '1791400015.000001 Failed',
        'le-connection-abort-by-local', '1791400015.000002 Disconnect',
        '1791400016.000001 InProgress']


def test_hci_filter_emits_only_fixed_events_roles_and_reason_bytes():
    if not shutil.which('bash') or not shutil.which('awk'):
        pytest.skip('Linux HCI output filter unavailable')
    script = Path(__file__).resolve().parents[2] / 'tools' / 'probe-bluetooth-link.sh'
    sample = '''> HCI Event: LE Meta Event (0x3e) plen 31
      LE Enhanced Connection Complete (0x0a)
        Status: Success (0x00)
        Handle: 66
        Role: Central (0x00)
        Peer address: AA:BB:CC:DD:EE:FF
> HCI Event: Encryption Change (0x08) plen 4
        Status: Authentication Failure (0x05)
        Key: PRIVATE_KEY_VALUE
< ACL Data TX: Handle 66
        Status: Private payload (0x42)
> HCI Event: LE Meta Event (0x3e) plen 10
      LE Advertising Report (0x02)
        Status: Private report (0x43)
> HCI Event: Disconnect Complete (0x05) plen 4
        Status: Success (0x00)
        Handle: 66
        Reason: Remote User Terminated Connection (0x13)
        Name: PRIVATE_PHONE_NAME
> HCI Event: LE Meta Event (0x3e) plen 19
      LE Connection Complete (0x01)
        Status: Success (0x00)
        Role: Peripheral (0x01)
'''
    result = subprocess.run(['bash', str(script), '--filter-only'], input=sample,
                            capture_output=True, text=True, check=True, timeout=5)
    assert result.stdout.splitlines() == [
        'LE link event', 'Status: (0x00)', 'Pi role: Central',
        'Encryption event', 'Status: (0x05)', 'Disconnect event',
        'Status: (0x00)', 'Reason: (0x13)', 'LE link event',
        'Status: (0x00)', 'Pi role: Peripheral']


@pytest.mark.asyncio
@pytest.mark.parametrize('success', [False, True])
async def test_passive_probe_correlates_bluez_reply_without_sending_device_methods(success):
    if not shutil.which('dbus-daemon'):
        pytest.skip('private bus unavailable')
    result = subprocess.run(['dbus-daemon', '--session', '--fork', '--print-address=1',
                             '--print-pid=1'], check=True, capture_output=True, text=True, timeout=5)
    address, pid = result.stdout.strip().splitlines()
    buses = []
    task = None
    shell_monitor = None
    calls = []
    output = []

    class Phone(ServiceInterface):
        def __init__(self):
            super().__init__('org.bluez.Device1')

        @method()
        def Connect(self):
            calls.append('Connect')
            if not success:
                raise DBusError('org.bluez.Error.Failed', 'le-connection-refused')

        @method()
        def Disconnect(self):
            calls.append('Disconnect')

    try:
        for _ in range(3):
            buses.append(await MessageBus(bus_address=address).connect())
        owner, watcher, client = buses
        await owner.request_name('org.bluez')
        owner.export('/phone', Phone())
        owner.export('/other_private_phone', Phone())
        ready = asyncio.Event()
        def emit(text, **kwargs):
            output.append(text)
            if text.startswith('Watching'):
                ready.set()
        task = asyncio.create_task(probe.monitor(watcher, '/phone', seconds=0.3, emit=emit))
        await asyncio.wait_for(ready.wait(), 3)
        if shutil.which('dbus-monitor') and shutil.which('bash'):
            shell_monitor = subprocess.Popen(['dbus-monitor', '--address', address,
                "type='error',sender='org.bluez'",
                "type='method_call',destination='org.bluez',interface='org.bluez.Device1',member='Connect'"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            await asyncio.sleep(0.15)  # Isolated monitor subscription startup only.
        reply = await client.call(Message(destination='org.bluez', path='/phone',
            interface='org.bluez.Device1', member='Connect'))
        assert reply.message_type == (MessageType.METHOD_RETURN if success else MessageType.ERROR)
        await client.call(Message(destination='org.bluez', path='/other_private_phone',
            interface='org.bluez.Device1', member='Connect'))
        await client.call(Message(destination='org.bluez', path='/phone',
            interface='org.bluez.Device1', member='Disconnect'))
        await asyncio.wait_for(task, 3)
        assert calls == ['Connect', 'Connect', 'Disconnect']  # Test client only, not watcher.
        assert 'Connect #1 caller 1 observed' in output
        assert 'Disconnect #2 caller 1 observed' in output
        assert sum('Connect #' in line and 'observed' in line for line in output) == 1
        assert any(('returned successfully (not ANCS authorization)' if success else
                    'Failed: le-connection-refused') in line for line in output)
        assert not any('/phone' in line or address in line for line in output)
        if shell_monitor:
            shell_monitor.terminate()
            raw, _ = shell_monitor.communicate(timeout=3)
            script = Path(__file__).resolve().parents[2] / 'tools' / 'probe-bluetooth-reconnect-errors.sh'
            filtered = subprocess.run(['bash', str(script), '--filter-only'], input=raw,
                capture_output=True, text=True, check=True, timeout=5).stdout
            assert ' Connect\n' in filtered
            if not success:
                assert ' Failed\n' in filtered and 'le-connection-refused\n' in filtered
            assert '/phone' not in filtered and address not in filtered
    finally:
        if shell_monitor and shell_monitor.poll() is None:
            shell_monitor.terminate()
            shell_monitor.communicate(timeout=3)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        for bus in buses:
            bus.disconnect()
            await bus.wait_for_disconnect()
        os.kill(int(pid), signal.SIGTERM)
