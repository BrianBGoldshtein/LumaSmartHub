"""Durable night/wake timing, independent of the physical panel driver.

The caller supplies the effective sleep interval after calendar/command overrides.
Only transitions are saved. Live ramps use monotonic time; recovery requires UTC
verified for this boot. This module never runs DDC, speaks, or unlocks privacy.
"""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import math
import time
from uuid import uuid4


MODES = frozenset({'day', 'night-clock', 'off', 'waking'})
RAMP_KINDS = frozenset({'scheduled', 'morning', 'temporary'})


def _date(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('An aware timestamp is required')
    return result.astimezone(UTC)


def _level(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError('Brightness must be a finite percentage')
    return float(value)


def ramp_level(start, target, elapsed, duration):
    """Smooth endpoints, with bounded output; the clock is not a wall clock."""
    progress = max(0., min(1., elapsed / duration))
    eased = progress * progress * (3 - 2 * progress)
    return start + (target - start) * eased


class DisplayCycle:
    def __init__(self, storage, *, clock=time.monotonic):
        self.storage, self.clock = storage, clock
        self.day_brightness, self.night_brightness, self.night_clock = 70., 5., True
        self.trusted = False
        self.blocked = True
        self.note = 'Waiting for the system clock.'
        self._manual_session = False
        self._ramp_origin = None
        self._restore_pending = True
        self.data = {'version': 1, 'mode': 'day', 'held_off': False, 'sleep_until': None,
                     'ramp': None, 'saved_at': None, 'last_morning_at': None}
        raw = storage.get_cache('display', 'cycle')
        try:
            if raw is not None:
                self.data = self._validate(raw)
        except (KeyError, ValueError, TypeError, OverflowError):
            # Damaged recovery state must not brighten the room automatically.
            self.data['held_off'] = True
            self.data['mode'] = 'off'
            self.note = 'Saved display state unavailable. Touch Wake to resume.'
        self._saved = deepcopy(self.data)

    @staticmethod
    def _validate(raw):
        if not isinstance(raw, dict) or raw.get('version') != 1 or raw.get('mode') not in MODES or type(raw.get('held_off')) is not bool:
            raise ValueError('Invalid display state')
        clean = {key: raw.get(key) for key in ('version', 'mode', 'held_off', 'sleep_until', 'saved_at', 'last_morning_at')}
        for key in ('sleep_until', 'saved_at', 'last_morning_at'):
            if clean[key] is not None:
                clean[key] = _date(clean[key]).isoformat()
        clean['ramp'] = None
        if raw.get('ramp') is not None:
            ramp = raw['ramp']
            if not isinstance(ramp, dict) or ramp.get('kind') not in RAMP_KINDS or not isinstance(ramp.get('id'), str) or len(ramp['id']) != 36:
                raise ValueError('Invalid wake ramp')
            duration = 300 if ramp['kind'] == 'scheduled' else 20
            if type(ramp.get('duration')) is not int or ramp['duration'] != duration or type(ramp.get('trusted')) is not bool:
                raise ValueError('Invalid wake duration')
            started = _date(ramp['started_at'])
            if clean['saved_at'] is None or started > _date(clean['saved_at']):
                raise ValueError('Invalid ramp start')
            clean['ramp'] = {'id': ramp['id'], 'kind': ramp['kind'], 'duration': duration,
                             'started_at': started.isoformat(), 'from': _level(ramp['from']),
                             'to': _level(ramp['to']), 'trusted': ramp['trusted']}
        if (clean['mode'] == 'waking') != bool(clean['ramp']) or (clean['held_off'] and clean['mode'] != 'off'):
            raise ValueError('Inconsistent display state')
        return clean

    def _save(self, now):
        # saved_at is not part of equality until a meaningful transition occurs.
        if self.data != self._saved:
            self.data['saved_at'] = now.astimezone(UTC).isoformat()
            self.storage.set_cache('display', 'cycle', self.data)
            self._saved = deepcopy(self.data)

    def _cancel_ramp(self):
        self.data['ramp'] = None
        self._ramp_origin = None

    def _restore(self, now):
        if not self._restore_pending:
            return
        self._restore_pending = False
        ramp = self.data['ramp']
        if ramp:
            if not ramp['trusted'] or (self.data['saved_at'] and now < _date(self.data['saved_at'])):
                self._cancel_ramp()
                self.data.update(mode='off', held_off=True)
                self.note = 'Wake recovery needs confirmation. Touch Wake to resume.'
            else:
                elapsed = max(0., (now - _date(ramp['started_at'])).total_seconds())
                self._ramp_origin = self.clock() - min(elapsed, ramp['duration'])

    def _begin(self, now, kind, start, *, started_at=None):
        duration = 300 if kind == 'scheduled' else 20
        began = started_at or now
        elapsed = max(0., min(duration, (now - began).total_seconds()))
        self.data.update(mode='waking', held_off=False,
                         ramp={'id': str(uuid4()), 'kind': kind, 'duration': duration,
                               'started_at': began.isoformat(), 'from': _level(start),
                               'to': self.day_brightness, 'trusted': self.trusted})
        self._ramp_origin = self.clock() - elapsed

    def _finish(self):
        if self.data['ramp'] and self._ramp_origin is not None and self.clock() - self._ramp_origin >= self.data['ramp']['duration']:
            self._cancel_ramp()
            self.data['mode'] = 'day'

    def brightness(self):
        if self.blocked or self.data['mode'] == 'off':
            return 0.
        if self.data['mode'] == 'night-clock':
            return min(self.night_brightness, self.day_brightness)
        ramp = self.data['ramp']
        if ramp and self._ramp_origin is not None:
            return ramp_level(ramp['from'], ramp['to'], self.clock() - self._ramp_origin, ramp['duration'])
        return self.day_brightness

    def sync(self, now, *, sleep_end, brightness, night_brightness=5, night_clock=True, trusted):
        now = now.astimezone(UTC)
        self.day_brightness, self.night_brightness = _level(brightness), _level(night_brightness)
        if type(night_clock) is not bool or type(trusted) is not bool:
            raise ValueError('Boolean display options required')
        self.night_clock, self.trusted = night_clock, trusted
        self.blocked = not trusted and not self._manual_session
        if self.blocked:
            return self.snapshot()
        self._restore(now)
        if self.note == 'Waiting for the system clock.':
            self.note = ''
        if not trusted and self.data['sleep_until'] and not self.data['held_off'] and self.data['mode'] in {'night-clock', 'off'}:
            # Manual Good night is allowed before clock sync. Its guessed wall
            # deadline must NOT subsequently authorize an automatic wake.
            self.data['mode'] = 'night-clock' if night_clock else 'off'
            self._save(now)
            return self.snapshot()
        old_end = _date(self.data['sleep_until']) if self.data['sleep_until'] else None
        end = sleep_end.astimezone(UTC) if sleep_end is not None else None
        sleeping = bool(end and end > now)
        self.data['sleep_until'] = end.isoformat() if sleeping else None
        if self.data['held_off']:
            self._cancel_ramp()
            self.data['mode'] = 'off'
        elif sleeping:
            self._cancel_ramp()
            self.data['mode'] = 'night-clock' if night_clock else 'off'
        elif old_end and self.data['mode'] in {'night-clock', 'off'}:
            # Tick latency does not shift the owner's actual sleep-end deadline.
            # Removing an active event makes its effective end the cancellation.
            start = min(self.night_brightness, self.day_brightness) if self.data['mode'] == 'night-clock' else 0.
            self._begin(now, 'scheduled', start, started_at=min(old_end, now))
        elif self.data['ramp'] and self.data['ramp']['to'] != self.day_brightness:
            # A new manual day brightness is authoritative; don't fight its slider.
            self._cancel_ramp()
            self.data['mode'] = 'day'
        elif not self.data['ramp']:
            self.data['mode'] = 'day'
        self._finish()
        self._save(now)
        return self.snapshot()

    def wake(self, now, *, morning=False):
        """Call after clearing the caller's sleep override. Returns briefing permission."""
        now = now.astimezone(UTC)
        current = self.brightness()
        was_blocked = self.blocked
        self.blocked = False
        self._manual_session = True
        self._restore_pending = False
        self.note = ''
        self.data['held_off'] = False
        self.data['sleep_until'] = None
        kind = 'morning' if morning else 'temporary'
        ramp = self.data['ramp']
        # Repeated commands in the same explicit ramp never move its deadline.
        if not ramp or ramp['kind'] != kind or self._ramp_origin is None:
            if current != self.day_brightness or was_blocked:
                self._begin(now, kind, current)
            else:
                self._cancel_ramp()
                self.data['mode'] = 'day'
        speak = False
        if morning:
            last = self.data['last_morning_at']
            speak = last is None or (now - _date(last)) >= timedelta(seconds=60)
            if speak:
                self.data['last_morning_at'] = now.isoformat()
        self._save(now)
        return speak

    def night(self, now, *, until):
        """Good night cancels any manual off/ramp and enters its effective interval."""
        self._cancel_ramp()
        self._restore_pending = False
        self._manual_session = True
        self.blocked = False
        self.note = ''
        self.data.update(held_off=False, mode='night-clock' if self.night_clock else 'off', sleep_until=until.astimezone(UTC).isoformat())
        self._save(now)

    def off(self, now):
        self._cancel_ramp()
        self.data.update(mode='off', held_off=True)
        self._save(now)

    def manual_brightness(self, now, value):
        self.day_brightness = _level(value)
        if self.data['mode'] == 'waking':
            self._cancel_ramp()
            self.data['mode'] = 'day'
        self._save(now)

    def snapshot(self):
        mode = 'off' if self.blocked else self.data['mode']
        ramp = self.data['ramp'] if mode == 'waking' else None
        elapsed = max(0., min(ramp['duration'], self.clock() - self._ramp_origin)) if ramp and self._ramp_origin is not None else 0.
        return {'mode': mode, 'brightness': self.brightness(), 'day_brightness': self.day_brightness,
                'night_brightness': min(self.night_brightness, self.day_brightness),
                'awaiting_clock': not self.trusted, 'note': self.note,
                'quiet': mode in {'night-clock', 'off'} or bool(ramp and ramp['kind'] == 'scheduled'),
                'ramp': {'id': ramp['id'], 'kind': ramp['kind'], 'duration_seconds': ramp['duration'],
                         'elapsed_seconds': elapsed, 'from_brightness': ramp['from'], 'to_brightness': ramp['to']} if ramp else None}
