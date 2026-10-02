"""One durable timer. Monotonic while alive; verified UTC only for recovery."""
from __future__ import annotations

import math
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from .models import CommandResult

TIMER_COMMANDS = frozenset({'start_timer', 'pause_timer', 'resume_timer', 'cancel_timer', 'show_timer', 'dismiss_timer'})


def _date(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('Timezone required')
    return result.astimezone(UTC)


class FocusTimer:
    def __init__(self, storage, *, clock=time.monotonic):
        self.storage, self.clock = storage, clock
        self.trusted = False
        self.end = None
        self.chime_until = None
        self.note = ''
        self.data = {'version': 1, 'status': 'idle', 'id': None, 'label': 'Timer', 'duration': 0,
                     'remaining': 0, 'deadline': None, 'saved_at': None, 'trusted': False}
        raw = storage.get_cache('timer', 'active')
        try:
            if not raw:
                return
            if not isinstance(raw, dict) or raw.get('version') != 1 or raw.get('status') not in {'idle','running','paused','complete'}:
                raise ValueError()
            if raw['status'] == 'idle':
                return
            if raw['status'] != 'idle':
                if not isinstance(raw.get('id'), str) or len(raw['id']) != 36:
                    raise ValueError()
                if not isinstance(raw.get('label'), str) or not 1 <= len(raw['label']) <= 40 or any(ord(c)<32 for c in raw['label']):
                    raise ValueError()
                for key in ('duration', 'remaining'):
                    if type(raw.get(key)) not in (int,float) or not math.isfinite(raw[key]) or not 0 <= raw[key] <= 14400:
                        raise ValueError()
                if raw['duration'] < 1 or raw['remaining'] > raw['duration']:
                    raise ValueError()
                _date(raw['saved_at'])
                if raw['status'] == 'running':
                    _date(raw['deadline'])
            self.data.update({key: raw[key] for key in self.data if key in raw})
            self.data['trusted'] = raw.get('trusted') is True
            if self.data['status'] == 'running':
                self.note = 'Waiting for the system clock before restoring this timer.'
        except (ValueError, TypeError, KeyError, OverflowError):
            self.note = 'The saved timer could not be restored. Start a new timer.'
            # Do not let malformed persisted data reach the wall or arithmetic.
            self.data = {'version': 1, 'status': 'idle', 'id': None, 'label': 'Timer', 'duration': 0,
                         'remaining': 0, 'deadline': None, 'saved_at': None, 'trusted': False}

    def remaining(self):
        return max(0, self.end-self.clock()) if self.end is not None else self.data['remaining']

    def _save(self, now):
        self.data['remaining'] = self.remaining()
        self.data['saved_at'] = now.isoformat()
        self.storage.set_cache('timer', 'active', dict(self.data))

    def _complete(self, now, *, sound=False):
        self.end = None
        self.data.update(status='complete', remaining=0, deadline=None)
        self.chime_until = self.clock()+10 if sound else None
        self._save(now)

    def tick(self, now=None, *, trusted=None):
        now = now or datetime.now(UTC)
        if trusted is not None:
            self.trusted = bool(trusted)
        if self.data['status'] != 'running':
            return False
        if self.end is None:  # Recovered process: never trust Pi's boot clock implicitly.
            if not self.trusted:
                return False
            if not self.data['trusted'] or now < _date(self.data['saved_at'])-timedelta(seconds=5):
                self.data.update(status='paused', deadline=None)
                self.note = 'Clock changed while Luma was offline. Review the remaining time, then resume or restart.'
                self._save(now)
            else:
                remaining = min(self.data['duration'], max(0, (_date(self.data['deadline'])-now).total_seconds()))
                if remaining == 0:
                    self._complete(now)  # Never replay a completion after restart.
                    self.note = 'Finished while Luma was offline.'
                else:
                    self.end = self.clock()+remaining
                    self.note = ''
            return True
        remaining = self.remaining()
        if remaining <= 0:
            self.note = ''
            self._complete(now, sound=True)
            return True
        # NTP correction: keep monotonic countdown, repair only its recovery anchor.
        deadline = now+timedelta(seconds=remaining)
        if self.trusted and (not self.data['trusted'] or abs((deadline-_date(self.data['deadline'])).total_seconds()) > 3):
            self.data.update(deadline=deadline.isoformat(), trusted=True)
            self._save(now)
        return False

    def snapshot(self, *, private=False):
        state = self.data['status']
        if state == 'running' and self.end is None:
            state = 'awaiting_time'
        label = self.data['label']
        if private and label not in {'Focus', 'Break', 'Timer'}:
            label = 'Timer'
        return {'id': self.data['id'], 'status': state, 'label': label,
                'duration_seconds': self.data['duration'], 'remaining_seconds': math.ceil(self.remaining()),
                'note': self.note}

    def execute(self, name, value=None, *, now=None, focus=25, rest=5, source='local'):
        now = now or datetime.now(UTC)
        if name == 'show_timer':
            return CommandResult(True, 'Timer control opened.', data={'overlay': 'timer'})
        if name == 'start_timer':
            if value in ('focus','break'):
                value = {'minutes': focus if value == 'focus' else rest, 'label': 'Focus' if value == 'focus' else 'Break'}
            if type(value) is int:
                value = {'minutes': value}
            if not isinstance(value, dict) or set(value)-{'minutes','seconds','label','replace_id'}:
                raise ValueError('Use a timer duration from 1 second to 4 hours.')
            minutes, label = value.get('minutes'), value.get('label','Timer')
            if ('seconds' in value) == ('minutes' in value):
                raise ValueError('Choose minutes or seconds for the timer.')
            seconds = value['seconds'] if 'seconds' in value else minutes * 60 if type(minutes) is int else None
            if type(seconds) is not int or not 1 <= seconds <= 14400:
                raise ValueError('Use a timer duration from 1 second to 4 hours.')
            if not isinstance(label,str) or not 1 <= len(label.strip()) <= 40 or any(ord(c)<32 for c in label):
                raise ValueError('Use a timer label of 1 to 40 characters.')
            if source in {'voice','siri'} and 'replace_id' in value:
                raise ValueError('Replace timers on the screen.')
            active = self.data['status'] in {'running','paused'}
            if active and value.get('replace_id') != self.data['id']:
                return CommandResult(False, 'A timer is already active. Confirm replacement on the screen.',
                                     data={'overlay':'timer','confirmation_required':True})
            if 'replace_id' in value and (not active or value['replace_id'] != self.data['id']):
                return CommandResult(False, 'The timer changed. Review it before starting again.', data={'overlay':'timer'})
            self.end = self.clock()+seconds
            self.data.update(status='running', id=str(uuid4()), label=label.strip(), duration=seconds,
                             deadline=(now+timedelta(seconds=seconds)).isoformat(), trusted=self.trusted)
            self.chime_until = None
            self.note = ''
        elif name == 'pause_timer' and self.data['status'] == 'running':
            self.data['remaining'] = self.remaining()
            self.end = None
            self.data.update(status='paused', deadline=None)
            self.note = ''
        elif name == 'resume_timer' and self.data['status'] == 'paused':
            self.end = self.clock()+self.data['remaining']
            self.data.update(status='running', deadline=(now+timedelta(seconds=self.data['remaining'])).isoformat(), trusted=self.trusted)
            self.note = ''
        elif name == 'cancel_timer' or (name == 'dismiss_timer' and self.data['status'] == 'complete'):
            self.end = None
            self.chime_until = None
            self.data.update(status='idle', id=None, label='Timer', duration=0, remaining=0, deadline=None)
            self.note = ''
        else:
            return CommandResult(False, 'That timer action is not available right now.', data={'overlay':'timer'})
        self._save(now)
        return CommandResult(True, 'Timer updated.', True)

    def claim_chime(self, *, muted=False):
        pending, self.chime_until = self.chime_until, None  # At most once, even across bridge retries.
        return bool(not muted and pending is not None and self.clock() <= pending and self.data['status']=='complete')
