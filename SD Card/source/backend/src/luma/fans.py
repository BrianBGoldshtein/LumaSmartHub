"""Two saved IR fans, explicit button semantics and durable no-replay receipts.

No device access here. Learning never enables a scene or remote control. Proofs
are owner observations, not IR acknowledgments, and bind to both output routes.
"""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
import json
from threading import RLock
from uuid import UUID, uuid4

from .ir_protocol import clean_text, validate_result
from .ir_signal import signal, signal_key
from .room import instant

SLOTS = ('fan_1', 'fan_2')
BUTTONS = {
    'power_on': ('On', 'absolute'), 'power_off': ('Off', 'absolute'),
    'power_toggle': ('Power toggle', 'toggle'),
    **{f'speed_{n}': (f'Speed {n}', 'absolute') for n in range(1, 7)},
    'speed_up': ('Speed up', 'relative'), 'speed_down': ('Speed down', 'relative'),
    'oscillation_on': ('Oscillation on', 'absolute'), 'oscillation_off': ('Oscillation off', 'absolute'),
    'oscillation_toggle': ('Oscillation toggle', 'toggle'),
    'horizontal_toggle': ('Horizontal swing', 'toggle'), 'vertical_toggle': ('Vertical swing', 'toggle'),
}


def slot_key(value):
    if not isinstance(value, str) or value not in SLOTS: raise ValueError('Choose Fan 1 or Fan 2.')
    return value


def button_key(value):
    if not isinstance(value, str) or value not in BUTTONS: raise ValueError('Choose a supported remote button.')
    return value


def uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value: raise ValueError('Invalid saved identifier.')
    return value


def route(value):
    if not isinstance(value, dict) or set(value) != {'device', 'emitter'}: raise ValueError('Choose a discovered output.')
    device = validate_result('discover', {'devices': [value['device']]})['devices'][0]
    if not device['send']: raise ValueError('This adapter cannot transmit raw infrared.')
    emitter = value['emitter']
    if device['emitter_selection']:
        if type(emitter) is not int or not 1 <= emitter <= 32: raise ValueError('Choose one emitter channel.')
    elif emitter is not None: raise ValueError('This adapter has one unselectable output.')
    return deepcopy(value)


def basis(slots, fan, key):
    # Names are cosmetic; changing either physical output invalidates all proofs.
    paths = {slot: ({'id': slots[slot]['route']['device']['id'], 'emitter': slots[slot]['route']['emitter']}
                    if slots[slot] else None) for slot in SLOTS}
    data = [paths, fan, key, signal_key(slots[fan]['buttons'][key]['signal'])]
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Fans:
    def __init__(self, storage):
        self.storage, self.lock = storage, RLock()
        self.generation, self.revision = str(uuid4()), str(uuid4())
        self.slots = dict.fromkeys(SLOTS)
        self.receipts = dict.fromkeys(SLOTS)
        self.overrides = dict.fromkeys(SLOTS)
        self.recovery_error = False
        try:
            raw = storage.get_cache('room', 'fans')
            if raw is not None:
                self._validate(raw)
                self.revision, self.slots, self.receipts, self.overrides = (raw[key] for key in ('revision', 'slots', 'receipts', 'overrides'))
        except Exception:
            self.recovery_error = True  # Preserve corrupt data, no replacement writes.

    @staticmethod
    def _validate(raw):
        if (not isinstance(raw, dict) or set(raw) != {'version', 'revision', 'slots', 'receipts', 'overrides'}
                or type(raw['version']) is not int or raw['version'] != 1): raise ValueError()
        uuid(raw['revision'])
        for name in ('slots', 'receipts', 'overrides'):
            if not isinstance(raw[name], dict) or set(raw[name]) != set(SLOTS): raise ValueError()
        for fan in SLOTS:
            row = raw['slots'][fan]
            if row is not None:
                if not isinstance(row, dict) or set(row) != {'name', 'route', 'buttons'} or not clean_text(row['name'], 40): raise ValueError()
                route(row['route'])
                if not isinstance(row['buttons'], dict) or len(row['buttons']) > len(BUTTONS): raise ValueError()
                for key, item in row['buttons'].items():
                    button_key(key)
                    if not isinstance(item, dict) or set(item) != {'signal', 'checks', 'basis'}: raise ValueError()
                    signal(item['signal'])
                    if type(item['checks']) is not int or not 0 <= item['checks'] <= 2: raise ValueError()
                    if item['basis'] != (basis(raw['slots'], fan, key) if item['checks'] else None): raise ValueError()
            receipt = raw['receipts'][fan]
            if receipt is not None:
                if not isinstance(receipt, dict) or set(receipt) != {'id', 'button', 'basis', 'kind', 'status', 'at', 'observed'}: raise ValueError()
                uuid(receipt['id']); button_key(receipt['button'])
                if (receipt['kind'] not in ('test', 'manual', 'scene') or receipt['status'] not in ('unknown', 'not_sent', 'sent_unconfirmed')
                        or not instant(receipt['at']) or type(receipt['observed']) is not bool
                        or not isinstance(receipt['basis'], str) or len(receipt['basis']) != 64
                        or any(c not in '0123456789abcdef' for c in receipt['basis'])): raise ValueError()
            until = raw['overrides'][fan]
            if until is not None and not instant(until): raise ValueError()

    def check(self, revision, generation=None):
        if self.recovery_error: raise ValueError('Fan settings need recovery. Nothing was overwritten.')
        if revision != self.revision or generation is not None and generation != self.generation:
            raise ValueError('Fan settings changed. Reload before continuing.')

    def _save(self, slots=None, receipts=None, overrides=None, *, revise=False):
        raw = {'version': 1, 'revision': str(uuid4()) if revise else self.revision,
               'slots': deepcopy(self.slots if slots is None else slots),
               'receipts': deepcopy(self.receipts if receipts is None else receipts),
               'overrides': deepcopy(self.overrides if overrides is None else overrides)}
        self._validate(raw)
        self.storage.set_cache('room', 'fans', raw)
        self.revision, self.slots, self.receipts, self.overrides = (raw[key] for key in ('revision', 'slots', 'receipts', 'overrides'))

    def select(self, fan, name, output, *, revision, generation):
        slot_key(fan)
        if output is not None:
            output = route(output)
            if not clean_text(name, 40) or not name.strip(): raise ValueError('Use a fan name of 1 to 40 characters.')
        with self.lock:
            self.check(revision, generation)
            slots = deepcopy(self.slots)
            old = slots[fan]
            same_route = bool(old and output == old['route'])
            slots[fan] = {'name': name.strip(), 'route': output, 'buttons': old['buttons'] if same_route else {}} if output else None
            if not same_route:
                for row in slots.values():
                    if row:
                        for item in row['buttons'].values(): item.update(checks=0, basis=None)
            receipts = {**self.receipts, fan: None}
            self._save(slots, receipts, revise=True)  # Preserve manual overrides across edits.

    def learned(self, fan, key, raw, *, revision, generation):
        slot_key(fan); button_key(key)
        clean = signal(raw)
        with self.lock:
            self.check(revision, generation)
            if not self.slots[fan]: raise ValueError('Choose this fan output first.')
            slots = deepcopy(self.slots)
            slots[fan]['buttons'][key] = {'signal': clean, 'checks': 0, 'basis': None}
            self._save(slots, {**self.receipts, fan: None}, revise=True)

    def forget(self, fan, key, *, revision, generation):
        slot_key(fan); button_key(key)
        with self.lock:
            self.check(revision, generation)
            if not self.slots[fan] or key not in self.slots[fan]['buttons']: raise ValueError('That button is not saved.')
            slots = deepcopy(self.slots)
            del slots[fan]['buttons'][key]
            self._save(slots, {**self.receipts, fan: None}, revise=True)

    def independent(self):
        return all(row and any(item['checks'] > 0 for item in row['buttons'].values()) for row in self.slots.values())

    def command(self, fan, key, *, kind, confirmed, now):
        slot_key(fan); button_key(key)
        if self.recovery_error: raise ValueError('Fan settings need recovery.')
        row = self.slots[fan]
        if not row or key not in row['buttons']: raise ValueError('Learn this remote button first.')
        item = row['buttons'][key]
        if kind not in ('test', 'manual', 'scene'): raise ValueError('Invalid fan action source.')
        if kind == 'test' and confirmed is not True: raise ValueError('Confirm you are ready to observe both fans during this test.')
        if kind == 'manual':
            if item['checks'] < 1: raise ValueError('Test this button before using it.')
            if (BUTTONS[key][1] != 'absolute' or not self.independent()) and confirmed is not True:
                raise ValueError('Confirm this one-time fan command and observe both fans.')
        if kind == 'scene':
            until = instant(self.overrides[fan])
            if until and now < until: raise ValueError('A manual fan override is still active.')
            if BUTTONS[key][1] != 'absolute' or item['checks'] < 2 or not self.independent():
                raise ValueError('Scenes require independently tested, repeatable absolute commands.')
        return {'action': 'send', 'device_id': row['route']['device']['id'],
                'emitter': row['route']['emitter'], 'signal': deepcopy(item['signal'])}

    def claim(self, fan, key, *, kind, confirmed, revision, generation, now):
        with self.lock:
            self.check(revision, generation)
            payload = self.command(fan, key, kind=kind, confirmed=confirmed, now=now)
            receipt = {'id': str(uuid4()), 'button': key, 'basis': basis(self.slots, fan, key),
                       'kind': kind, 'status': 'unknown', 'at': now.isoformat(), 'observed': False}
            overrides = deepcopy(self.overrides)
            if kind != 'scene': overrides[fan] = (now + timedelta(hours=1)).isoformat()
            self._save(receipts={**self.receipts, fan: receipt}, overrides=overrides)
            return receipt['id'], payload

    def finish(self, fan, identifier, status, *, revision, generation):
        slot_key(fan)
        if status not in ('unknown', 'not_sent', 'sent_unconfirmed'): raise ValueError('Invalid IR outcome.')
        with self.lock:
            if revision != self.revision or generation != self.generation: return False
            receipt = self.receipts[fan]
            if not receipt or receipt['id'] != identifier: return False
            self._save(receipts={**self.receipts, fan: {**receipt, 'status': status}})
            return True

    def observe(self, fan, identifier, expected_state, other_unchanged, *, revision, generation, now, repeat_same_state=False):
        slot_key(fan)
        if any(type(value) is not bool for value in (expected_state, other_unchanged, repeat_same_state)): raise ValueError('Confirm both observations.')
        with self.lock:
            self.check(revision, generation)
            receipt = self.receipts[fan]
            if (not receipt or receipt['id'] != identifier or receipt['kind'] != 'test' or receipt['status'] != 'sent_unconfirmed'
                    or receipt['observed'] or not timedelta(0) <= now - instant(receipt['at']) <= timedelta(minutes=2)):
                raise ValueError('Run a fresh one-button test before recording observations.')
            key = receipt['button']
            if (not self.slots[fan] or key not in self.slots[fan]['buttons']
                    or receipt['basis'] != basis(self.slots, fan, key)):
                raise ValueError('The fan output or button changed. Test it again.')
            slots = deepcopy(self.slots)
            if not expected_state or not other_unchanged:
                for row in slots.values():
                    if row:
                        for item in row['buttons'].values(): item.update(checks=0, basis=None)
            else:
                item = slots[fan]['buttons'][key]
                if BUTTONS[key][1] == 'absolute' and item['checks'] >= 1 and not repeat_same_state:
                    raise ValueError('For the second check, confirm the fan was already in this state and stayed there.')
                item.update(checks=min(2, item['checks'] + 1), basis=receipt['basis'])
            self._save(slots, {**self.receipts, fan: {**receipt, 'observed': True}}, revise=True)

    def configuration(self, now):
        with self.lock:
            rows = []
            for fan, row in self.slots.items():
                buttons = []
                if row:
                    for key, item in row['buttons'].items():
                        buttons.append({'key': key, 'label': BUTTONS[key][0], 'kind': BUTTONS[key][1], 'checks': item['checks'],
                                        'scene_eligible': bool(item['checks'] >= 2 and BUTTONS[key][1] == 'absolute' and self.independent())})
                until = instant(self.overrides[fan])
                rows.append({'id': fan, 'name': row['name'] if row else None, 'route': deepcopy(row['route']) if row else None,
                             'buttons': buttons, 'last_command': deepcopy(self.receipts[fan]),
                             'override_until': until.isoformat() if until and now < until else None})
            return {'revision': self.revision, 'recovery_error': self.recovery_error,
                    'independent': bool(self.independent()), 'fans': rows, 'remote_control': False}
