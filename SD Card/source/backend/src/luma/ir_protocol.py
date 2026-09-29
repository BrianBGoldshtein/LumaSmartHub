"""Strict one-line, bounded local IR protocol; never echoes an input payload."""
import json
import re

from .ir_signal import InfraredError, signal

MAX_WIRE = 16384
DEVICE_ID = re.compile(r'usb-ir-[a-f0-9]{24}')


class InfraredBusy(InfraredError):
    pass


class InfraredUnavailable(InfraredError):
    pass


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value: raise InfraredError('Invalid infrared message.')
        value[key] = item
    return value


def _constant(_):
    raise InfraredError('Invalid infrared message.')


def decode(raw):
    try:
        if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_WIRE or not raw.endswith(b'\n'):
            raise ValueError()
        if b'\n' in raw[:-1] or b'\r' in raw: raise ValueError()
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
        if not isinstance(value, dict): raise ValueError()
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise InfraredError('Invalid infrared message.') from None


def encode(value):
    try:
        raw = (json.dumps(value, separators=(',', ':'), allow_nan=False) + '\n').encode('ascii')
        if len(raw) > MAX_WIRE: raise ValueError()
        return raw
    except (ValueError, TypeError, RecursionError):
        raise InfraredError('Invalid infrared message.') from None


def clean_text(value, limit):
    return (isinstance(value, str) and 1 <= len(value) <= limit
            and not any(ord(char) < 32 or ord(char) == 127 or 0xD800 <= ord(char) <= 0xDFFF for char in value))


def validate_result(action, value):
    """Fail closed on malformed/unexpected helper output or accidental leakage."""
    bad = InfraredUnavailable('Infrared service returned an invalid response.')
    if not isinstance(value, dict): raise bad
    if set(value) == {'error'}:
        if not clean_text(value['error'], 200): raise bad
        # Worker errors are fixed local messages, never hardware/library payloads.
        return value
    if action == 'discover':
        if set(value) != {'devices'} or not isinstance(value['devices'], list) or len(value['devices']) > 16: raise bad
        ids = set()
        caps = {'serial_present', 'receive', 'send', 'measure_carrier', 'emitter_selection'}
        for row in value['devices']:
            if not isinstance(row, dict) or set(row) != {'id', 'name'} | caps: raise bad
            if not isinstance(row['id'], str) or not DEVICE_ID.fullmatch(row['id']) or row['id'] in ids: raise bad
            if not clean_text(row['name'], 100) or any(type(row[key]) is not bool for key in caps): raise bad
            if not (row['receive'] or row['send']): raise bad
            ids.add(row['id'])
        return value
    if action == 'learn':
        if set(value) != {'signal'} or not isinstance(value['signal'], dict): raise bad
        item = value['signal']
        if set(item) != {'carrier_hz', 'durations', 'carrier_source'} or item['carrier_source'] not in ('measured', 'owner_supplied'): raise bad
        try:
            clean = signal({key: item[key] for key in ('carrier_hz', 'durations')})
        except InfraredError:
            raise bad from None
        return {'signal': {**clean, 'carrier_source': item['carrier_source']}}
    if action == 'send':
        if set(value) != {'status', 'message'} or value['status'] not in ('sent_unconfirmed', 'unknown'): raise bad
        # No arbitrary worker text needed for command receipts.
        return send_result(value['status'])
    raise bad


def send_result(status='unknown'):
    return {'status': status, 'message': ('Command sent; IR device state is unconfirmed.' if status == 'sent_unconfirmed'
                                         else 'IR outcome is unknown. It will not be retried.')}
