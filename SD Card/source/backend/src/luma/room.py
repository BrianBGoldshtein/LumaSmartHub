"""Durable purifier selection/session and restart-safe command receipts.

Readings are memory-only. Scenes and IR have separate stores to be integrated;
connecting VeSync never authorizes either or remote device control.
"""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import re
from threading import RLock
from uuid import UUID, uuid4

from .purifier_adapter import CORE300_TYPES, credentials


def instant(value):
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.astimezone(UTC) if parsed.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def selected_device(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {'id', 'name', 'model'}:
        raise ValueError('Select a discovered purifier.')
    if not isinstance(value['id'], str) or not re.fullmatch(r'purifier-[a-f0-9]{24}', value['id']):
        raise ValueError('Select a discovered purifier.')
    if value['model'] not in CORE300_TYPES:
        raise ValueError('Select a supported Core 300S purifier.')
    if not isinstance(value['name'], str) or not 1 <= len(value['name'].strip()) <= 100 or re.search(r'[\x00-\x1f\x7f]', value['name']):
        raise ValueError('Use a device name of 1 to 100 characters.')
    return {**value, 'name': value['name'].strip()}


class Room:
    def __init__(self, storage):
        self.storage = storage
        self.lock = RLock()
        self.generation = str(uuid4())
        self.revision = str(uuid4())
        self.selected = None
        self._session = None
        self.recovery_error = False
        self.receipt = None
        self.override_until = None
        self.sample = None
        self.health = 'not_connected'
        try:
            raw = storage.get_cache('room', 'purifier')
            if raw is not None:
                if not isinstance(raw, dict) or set(raw) != {'version', 'revision', 'selected'} or raw['version'] != 1:
                    raise ValueError()
                if str(UUID(raw['revision'])) != raw['revision']:
                    raise ValueError()
                self.revision = raw['revision']
                self.selected = selected_device(raw['selected'])
            secret = storage.get_secret('room.vesync')
            if secret is not None:
                self._session = credentials(json.loads(secret))
                self.health = 'unavailable'
            receipt = storage.get_cache('room', 'purifier_command')
            if receipt is not None:
                if (not isinstance(receipt, dict) or set(receipt) != {'id', 'device_id', 'action', 'value', 'status', 'accepted', 'at', 'override_until'}
                        or str(UUID(receipt['id'])) != receipt['id'] or not instant(receipt['at'])
                        or not instant(receipt['override_until']) or receipt['status'] not in ('confirmed', 'unconfirmed', 'rejected', 'not_sent')
                        or receipt['accepted'] is not None and type(receipt['accepted']) is not bool):
                    raise ValueError()
                self._action(receipt['action'], receipt['value'])
                if not isinstance(receipt['device_id'], str) or not re.fullmatch(r'purifier-[a-f0-9]{24}', receipt['device_id']):
                    raise ValueError()
                self.receipt = receipt
            override = storage.get_cache('room', 'purifier_override')
            if override is not None and not instant(override):
                raise ValueError()
            # Read older receipts without a migration write on every startup.
            # The next edit/claim preserves this deadline in its own record.
            self.override_until = override or (receipt['override_until'] if receipt else None)
        except Exception:
            # No overwrite/reinitialization of damaged evidence. All configuration
            # and device commands stay disabled until deliberate recovery.
            self.recovery_error = True
            self.selected = None
            self._session = None
            self.receipt = None
            self.override_until = None
            self.health = 'recovery_required'

    @property
    def session(self):
        with self.lock:
            return deepcopy(self._session)

    def check(self, revision, generation=None):
        if self.recovery_error:
            raise ValueError('Room settings need recovery. Nothing was overwritten.')
        if revision != self.revision or generation is not None and generation != self.generation:
            raise ValueError('Room settings changed. Reload before continuing.')

    def _write(self, connection, revision, selected):
        connection.execute("INSERT INTO cache(namespace,key,payload,updated_at) VALUES('room','purifier',?,?) ON CONFLICT(namespace,key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
                           (json.dumps({'version': 1, 'revision': revision, 'selected': selected}), datetime.now(UTC).isoformat()))
        self._write_override(connection, self.override_until)

    @staticmethod
    def _write_override(connection, until):
        if until is not None:
            connection.execute("INSERT INTO cache(namespace,key,payload,updated_at) VALUES('room','purifier_override',?,?) ON CONFLICT(namespace,key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
                               (json.dumps(until), datetime.now(UTC).isoformat()))

    def set_session(self, value, *, revision, generation):
        clean = credentials(value) if value is not None else None
        with self.lock:
            self.check(revision, generation)
            # Never carry a device selection/automation permission to a different
            # account. Reconnection still requires explicit device selection.
            new_revision = str(uuid4())
            with self.storage.transaction() as connection:
                if clean is None:
                    connection.execute("DELETE FROM secrets WHERE key='room.vesync'")
                else:
                    connection.execute("INSERT INTO secrets(key,payload,updated_at) VALUES('room.vesync',?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
                                       (json.dumps(clean), datetime.now(UTC).isoformat()))
                self._write(connection, new_revision, None)
                connection.execute("DELETE FROM cache WHERE namespace='room' AND key='purifier_command'")
            self._session = clean
            self.revision = new_revision
            self.generation = str(uuid4())
            self.selected = self.sample = self.receipt = None
            self.health = 'unavailable' if clean else 'not_connected'

    def select(self, value, *, revision, generation):
        clean = selected_device(value)
        with self.lock:
            self.check(revision, generation)
            if clean is not None and self._session is None:
                raise ValueError('Connect VeSync before selecting a purifier.')
            new_revision = str(uuid4())
            with self.storage.transaction() as connection:
                self._write(connection, new_revision, clean)
                connection.execute("DELETE FROM cache WHERE namespace='room' AND key='purifier_command'")
            self.revision, self.selected = new_revision, clean
            self.sample = self.receipt = None

    def report(self, value, *, generation, revision):
        with self.lock:
            if generation != self.generation or revision != self.revision or not self.selected or value['id'] != self.selected['id']:
                return False
            self.sample = deepcopy(value)
            self.health = 'ready'
            return True

    @staticmethod
    def _action(action, value):
        if not ((action in ('power', 'display') and type(value) is bool)
                or (action == 'speed' and type(value) is int and value in (1, 2, 3))
                or (action == 'mode' and type(value) is str and value in ('manual', 'sleep', 'auto'))):
            raise ValueError('Choose a supported purifier action.')

    def override_active(self, now):
        until = instant(self.override_until)
        return bool(until and now < until)

    def claim(self, action, value, *, revision, generation, now, kind='manual'):
        self._action(action, value)
        if kind not in ('manual', 'scene'):
            raise ValueError('Invalid purifier command source.')
        with self.lock:
            self.check(revision, generation)
            if not self.selected:
                raise ValueError('Select a purifier first.')
            if kind == 'scene' and self.override_active(now):
                raise ValueError('A manual purifier override is still active.')
            # Claim durably BEFORE sending. A restart cannot replay this receipt;
            # an interrupted request is left explicitly unconfirmed.
            until = (now + timedelta(hours=1)).isoformat() if kind == 'manual' else self.override_until
            receipt = {'id': str(uuid4()), 'device_id': self.selected['id'], 'action': action, 'value': value,
                       'status': 'unconfirmed', 'accepted': None, 'at': now.isoformat(),
                       'override_until': until or now.isoformat()}
            # Receipt and manual suppression are one durable transaction. Scene
            # receipts do not extend suppression; edits cannot erase it.
            with self.storage.transaction() as connection:
                connection.execute("INSERT INTO cache(namespace,key,payload,updated_at) VALUES('room','purifier_command',?,?) ON CONFLICT(namespace,key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
                                   (json.dumps(receipt), datetime.now(UTC).isoformat()))
                self._write_override(connection, until)
            self.receipt = receipt
            self.override_until = until
            return receipt['id']

    def finish(self, identifier, result, *, generation, revision):
        with self.lock:
            if generation != self.generation or revision != self.revision or not self.receipt or self.receipt['id'] != identifier:
                return False
            if result['status'] not in ('confirmed', 'unconfirmed', 'rejected', 'not_sent') or result['accepted'] is not None and type(result['accepted']) is not bool:
                raise ValueError('Invalid command outcome.')
            receipt = {**self.receipt, 'status': result['status'], 'accepted': result['accepted']}
            self.storage.set_cache('room', 'purifier_command', receipt)
            self.receipt = receipt
            return True

    def view(self, now):
        with self.lock:
            if not self.selected:
                return None
            sample = deepcopy(self.sample)
            at = instant(sample['reported_at']) if sample else None
            fresh = bool(at and timedelta(0) <= now - at <= timedelta(minutes=5) and self.health == 'ready')
            # Fresh capabilities required before UI offers controls. Saved readings
            # may be shown as stale, but never infer a successful current connection.
            return {'device': deepcopy(self.selected), 'health': self.health if fresh or self.health != 'ready' else 'stale',
                    'fresh': fresh, 'reported_at': sample['reported_at'] if sample else None,
                    'state': sample['state'] if sample else None, 'capabilities': sample['capabilities'] if fresh else None,
                    'last_command': deepcopy(self.receipt)}

    def configuration(self, now):
        with self.lock:
            return {'revision': self.revision, 'connected': self._session is not None, 'selected': deepcopy(self.selected),
                    'recovery_error': self.recovery_error, 'purifier': self.view(now), 'remote_control': False}
