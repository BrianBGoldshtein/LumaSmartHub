#!/usr/bin/env python3
"""Observe selected-phone Connect/Disconnect errors without initiating a link.

Run with the Pi's installed venv Python as root. Only fixed method/error labels,
allowlisted BlueZ reason codes and durations are emitted. No raw D-Bus body,
phone identifier, notification, pairing secret or configuration is printed/saved.
"""
import asyncio
import json
import sqlite3
from time import monotonic

from dbus_next import BusType, Message, MessageType
from dbus_next.aio import MessageBus

ERRORS = frozenset('InProgress Failed NotReady AlreadyConnected NotConnected '
                  'NotAvailable NotSupported InvalidArguments AuthenticationFailed '
                  'AuthenticationRejected AuthenticationTimeout ConnectionAttemptFailed'.split())
REASONS = frozenset('le-connection-' + ending for ending in (
    'invalid-arguments', 'adapter-not-powered', 'not-supported', 'already-connected',
    'bad-socket', 'memory-allocation', 'busy', 'refused', 'create-socket', 'timeout',
    'concurrent-connection-limit', 'abort-by-remote', 'abort-by-local',
    'link-layer-protocol-error', 'gatt-browsing', 'key-missing', 'unknown')) | frozenset(
    'br-connection-' + ending for ending in (
    'already-connected', 'page-timeout', 'profile-unavailable', 'sdp-search',
    'create-socket', 'invalid-argument', 'adapter-not-powered', 'not-supported',
    'bad-socket', 'memory-allocation', 'busy', 'concurrent-connection-limit',
    'timeout', 'refused', 'aborted-by-remote', 'aborted-by-local',
    'lmp-protocol-error', 'canceled', 'key-missing', 'unknown'))


def error_label(message):
    suffix = (message.error_name or '').removeprefix('org.bluez.Error.')
    name = suffix if message.error_name == 'org.bluez.Error.' + suffix and suffix in ERRORS else 'Other error'
    reason = next((value for value in message.body if isinstance(value, str) and value in REASONS), '')
    return name + (': ' + reason if reason else '')


async def monitor(bus, phone_path, *, seconds=45, emit=print, clock=monotonic):
    pending = {}
    callers = {}
    observations = 0

    def observe(message):
        nonlocal observations
        if message.message_type == MessageType.METHOD_CALL:
            if (message.path == phone_path and message.interface == 'org.bluez.Device1'
                    and message.member in ('Connect', 'Disconnect')):
                if len(pending) >= 32:
                    pending.pop(next(iter(pending)))
                observations += 1
                caller = callers.setdefault(message.sender, len(callers) + 1)
                label = f'{message.member} #{observations} caller {caller}'
                pending[(message.sender, message.serial)] = (label, clock())
                emit(label + ' observed', flush=True)
            # Monitoring clients must never reply to the observed method calls.
            return True
        if message.message_type in (MessageType.ERROR, MessageType.METHOD_RETURN) and message.destination != bus.unique_name:
            operation = pending.pop((message.destination, message.reply_serial), None)
            if operation:
                label, started = operation
                outcome = ('error: ' + error_label(message) if message.message_type == MessageType.ERROR
                           else 'returned successfully (not ANCS authorization)')
                emit(f'{label} after {clock() - started:.1f}s: {outcome}', flush=True)
            return True
        if (message.message_type == MessageType.SIGNAL and message.path == phone_path
                and message.interface == 'org.freedesktop.DBus.Properties'
                and message.member == 'PropertiesChanged' and len(message.body) == 3
                and message.body[0] == 'org.bluez.Device1'):
            values = message.body[1]
            for key in ('Connected', 'ServicesResolved'):
                value = values.get(key)
                if value is not None and value.signature == 'b':
                    emit(f'{key}: {value.value}', flush=True)
            return True
        return False  # Let our own BecomeMonitor reply resolve.

    bus.add_message_handler(observe)
    try:
        rules = [f"type='method_call',destination='org.bluez',path='{phone_path}',"
                 "interface='org.bluez.Device1',member='" + member + "'"
                 for member in ('Connect', 'Disconnect')]
        rules.append("type='error',sender='org.bluez'")
        rules.append("type='method_return',sender='org.bluez'")
        rules.append(f"type='signal',sender='org.bluez',path='{phone_path}',"
                     "interface='org.freedesktop.DBus.Properties',member='PropertiesChanged'")
        reply = await asyncio.wait_for(bus.call(Message(destination='org.freedesktop.DBus',
            path='/org/freedesktop/DBus', interface='org.freedesktop.DBus.Monitoring',
            member='BecomeMonitor', signature='asu', body=[rules, 0])), 5)
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError('Monitoring unavailable')
        emit(f'Watching selected-phone retries for {seconds:g} seconds. Do not tap Connect.', flush=True)
        await asyncio.sleep(seconds)
        if not observations:
            emit('No selected-phone Connect/Disconnect call observed in this window.', flush=True)
        for label, started in pending.values():
            emit(f'{label}: no reply observed after {clock() - started:.1f}s', flush=True)
        emit('Observation finished; no link requests or settings changes made.', flush=True)
    finally:
        bus.remove_message_handler(observe)


async def main():
    with sqlite3.connect('file:/var/lib/luma/luma.db?mode=ro', uri=True) as db:
        address = json.loads(db.execute('SELECT payload FROM settings WHERE id=1').fetchone()[0]).get('phone_address', '')
    if not address:
        raise RuntimeError('No selected phone')
    bus = await asyncio.wait_for(MessageBus(bus_type=BusType.SYSTEM).connect(), 5)
    try:
        reply = await asyncio.wait_for(bus.call(Message(destination='org.bluez', path='/',
            interface='org.freedesktop.DBus.ObjectManager', member='GetManagedObjects')), 5)
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError('Bluetooth unavailable')
        phone_path = next((path for path, entry in reply.body[0].items()
            if 'org.bluez.Device1' in entry and
            entry['org.bluez.Device1']['Address'].value.lower() == address.lower()), None)
        if not phone_path:
            raise RuntimeError('Selected phone unavailable')
        await monitor(bus, phone_path)
    finally:
        bus.disconnect()
        await bus.wait_for_disconnect()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as error:
        print('Observation stopped:', type(error).__name__, flush=True)
