"""Durable scene definitions and at-most-once execution journal.

No device, account, network or scheduler access. Callers must authorize each
trigger and revalidate each bound device immediately before dispatch. A saved
definition never grants remote access, and an interrupted run is never resumed.
"""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import re
from threading import RLock
from uuid import UUID, uuid4

from .room import Room, instant


def uuid(value):
    if not isinstance(value, str): raise ValueError('Invalid scene identifier.')
    UUID(value)

SCENES = ('morning', 'night', 'arrive', 'away')
AUTOMATIC = {'morning': 'calendar', 'night': 'calendar', 'arrive': 'presence', 'away': 'presence'}
OUTCOMES = ('confirmed', 'unconfirmed', 'rejected', 'not_sent', 'unavailable', 'skipped_override', 'cancelled')
MAX_RUNS = 40
MAX_ACTIONS = 8


def utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('A verified, timezone-aware clock is required.')
    return value.astimezone(UTC)


def scene_key(value):
    if not isinstance(value, str) or value not in SCENES:
        raise ValueError('Choose Morning, Night, Arrive or Away.')
    return value


def action(value):
    if (not isinstance(value, dict) or set(value) != {'device', 'action', 'value', 'binding'}
            or value['device'] != 'purifier'
            or not isinstance(value['binding'], str) or not re.fullmatch('[a-f0-9]{64}', value['binding'])):
        raise ValueError('Choose a linked device and a supported absolute action.')
    Room._action(value['action'], value['value'])
    return deepcopy(value)


def definition(value):
    if (not isinstance(value, dict) or set(value) != {'enabled', 'automatic', 'actions'}
            or type(value['enabled']) is not bool or type(value['automatic']) is not bool
            or not isinstance(value['actions'], list) or len(value['actions']) > MAX_ACTIONS):
        raise ValueError('Invalid scene settings.')
    actions = [action(item) for item in value['actions']]
    if (value['enabled'] and not actions) or (value['automatic'] and not value['enabled']):
        raise ValueError('Add actions before enabling a scene; automatic triggers need separate opt-in.')
    seen = set()
    for item in actions:
        key = item['action']
        # One instruction per physical property, not contradictory On/Off or
        # multiple speeds in the same run. Multiple different properties allowed.
        token = (item['device'], key)
        if token in seen:
            raise ValueError('Choose one setting per device property.')
        seen.add(token)
    purifier = {item['action']: item['value'] for item in actions if item['device'] == 'purifier'}
    if purifier.get('power') is False and ('speed' in purifier or 'mode' in purifier):
        raise ValueError('Purifier speed and mode can turn it on; do not combine them with Off.')
    bindings = {}
    for item in actions:
        previous = bindings.setdefault(item['device'], item['binding'])
        if previous != item['binding']:
            raise ValueError('Reload the device before adding another action.')
    return deepcopy(value)


class Scenes:
    def __init__(self, storage):
        self.storage, self.lock = storage, RLock()
        self.generation = str(uuid4())
        self.revision = str(uuid4())
        self.definitions = {key: {'enabled': False, 'automatic': False, 'actions': []} for key in SCENES}
        self.runs = []
        self.active = None  # Deliberately boot-local; no startup replay worker.
        self.recovery_error = False
        try:
            raw = storage.get_cache('room', 'scenes')
            if raw is not None:
                raw = self._without_unavailable_devices(raw)
                self.validate(raw)
                self.revision, self.definitions, self.runs = (raw[key] for key in ('revision', 'definitions', 'runs'))
        except Exception:
            self.recovery_error = True  # Preserve damaged records, disable writes.

    def _without_unavailable_devices(self, raw):
        """Retire unsupported device actions without losing unrelated scene settings."""
        if not isinstance(raw, dict) or not isinstance(raw.get('definitions'), dict) or not isinstance(raw.get('runs'), list):
            return raw
        cleaned = deepcopy(raw)
        changed = False
        for item in cleaned['definitions'].values():
            if not isinstance(item, dict) or not isinstance(item.get('actions'), list): return raw
            actions = item['actions']
            kept = [action for action in actions if isinstance(action, dict) and action.get('device') == 'purifier']
            if len(kept) != len(actions):
                item['actions'] = kept
                if not kept: item['enabled'] = item['automatic'] = False
                changed = True
        runs = cleaned['runs']
        kept_runs = [run for run in runs if isinstance(run, dict) and isinstance(run.get('steps'), list)
                     and all(isinstance(step, dict) and isinstance(step.get('action'), dict)
                             and step['action'].get('device') == 'purifier' for step in run['steps'])]
        if len(kept_runs) != len(runs):
            cleaned['runs'] = kept_runs
            changed = True
        if changed:
            cleaned['revision'] = str(uuid4())
            self.validate(cleaned)
            self.storage.set_cache('room', 'scenes', cleaned)
        return cleaned

    @staticmethod
    def validate(raw):
        if (not isinstance(raw, dict) or set(raw) != {'version', 'revision', 'definitions', 'runs'}
                or type(raw['version']) is not int or raw['version'] != 1):
            raise ValueError('Invalid scene store.')
        uuid(raw['revision'])
        if not isinstance(raw['definitions'], dict) or set(raw['definitions']) != set(SCENES):
            raise ValueError('Invalid scene store.')
        for item in raw['definitions'].values(): definition(item)
        if not isinstance(raw['runs'], list) or len(raw['runs']) > MAX_RUNS:
            raise ValueError('Invalid scene history.')
        ids = set()
        for run in raw['runs']:
            if (not isinstance(run, dict) or set(run) != {'id', 'scene', 'source', 'revision', 'at', 'finished', 'steps'}
                    or run['source'] not in ('manual', 'remote', 'calendar', 'presence')
                    or not instant(run['at']) or type(run['finished']) is not bool
                    or not isinstance(run['steps'], list) or not 1 <= len(run['steps']) <= MAX_ACTIONS):
                raise ValueError('Invalid scene history.')
            uuid(run['id']); uuid(run['revision']); scene_key(run['scene'])
            if run['id'] in ids or (run['source'] not in ('manual', 'remote') and run['source'] != AUTOMATIC[run['scene']]):
                raise ValueError('Invalid scene occurrence.')
            ids.add(run['id'])
            for step in run['steps']:
                if (not isinstance(step, dict) or set(step) != {'action', 'status'}
                        or step['status'] not in ('not_started', 'unknown', *OUTCOMES)):
                    raise ValueError('Invalid scene outcome.')
                action(step['action'])

    def check(self, revision, generation=None):
        if self.recovery_error:
            raise ValueError('Scene settings need recovery. Nothing was overwritten.')
        if revision != self.revision or generation is not None and generation != self.generation:
            raise ValueError('Scene settings changed. Reload before continuing.')

    def _save(self, *, definitions=None, runs=None, revise=False):
        raw = {'version': 1, 'revision': str(uuid4()) if revise else self.revision,
               'definitions': deepcopy(self.definitions if definitions is None else definitions),
               'runs': deepcopy(self.runs if runs is None else runs)}
        self.validate(raw)
        self.storage.set_cache('room', 'scenes', raw)
        self.revision, self.definitions, self.runs = (raw[key] for key in ('revision', 'definitions', 'runs'))

    def edit(self, key, value, *, revision):
        scene_key(key)
        clean = definition(value)
        with self.lock:
            self.check(revision)
            definitions = {**self.definitions, key: clean}
            self._save(definitions=definitions, revise=True)
            # In-flight I/O may already have happened. Keep its journal; the new
            # revision prevents every subsequent step of that old run.

    def claim(self, key, source, occurrence, *, revision, now, observed_at, trusted, remote_authorized=False):
        """Consume a fresh authorized occurrence BEFORE any step/device work.

        Occurrence IDs must be minted by a trusted caller, never a public event
        timestamp. Automatic transitions use the trigger monitor, not snapshots.
        """
        scene_key(key); uuid(occurrence)
        now, observed_at = utc(now), utc(observed_at)
        if trusted is not True or not timedelta(0) <= now - observed_at <= timedelta(seconds=15):
            raise ValueError('Scene trigger expired or clock is unverified. Nothing was queued.')
        with self.lock:
            self.check(revision)
            if self.active is not None:
                raise ValueError('A scene is already running. Nothing was queued.')
            config = self.definitions[key]
            if not config['enabled'] or not config['actions']:
                raise ValueError('This scene is disabled or empty.')
            if source == 'remote' and remote_authorized is not True:
                raise ValueError('This exact scene has not been explicitly allowlisted for remote control.')
            if source not in ('manual', 'remote', AUTOMATIC[key]) or source not in ('manual', 'remote') and not config['automatic']:
                raise ValueError('This automatic trigger is not enabled.')
            if any(run['id'] == occurrence for run in self.runs):
                raise ValueError('That scene occurrence was already consumed.')
            # Per-scene cooldown also survives restarts and editing. A backwards
            # clock cannot make a previous run suddenly eligible again.
            previous = [instant(run['at']) for run in self.runs if run['scene'] == key]
            if previous and now - max(previous) < timedelta(minutes=5):
                raise ValueError('This scene is cooling down. Nothing was queued.')
            run = {'id': occurrence, 'scene': key, 'source': source, 'revision': revision,
                   'at': now.isoformat(), 'finished': False,
                   'steps': [{'action': deepcopy(item), 'status': 'not_started'} for item in config['actions']]}
            self._save(runs=[*self.runs[-(MAX_RUNS - 1):], run])
            self.active = occurrence
            return deepcopy(run)

    def _run(self, identifier, generation):
        if self.recovery_error or generation != self.generation or self.active != identifier:
            raise ValueError('This scene run is no longer active; it will not be replayed.')
        index = next((i for i, run in enumerate(self.runs) if run['id'] == identifier and not run['finished']), None)
        if index is None: raise ValueError('Scene run is not active.')
        return index, self.runs[index]

    def begin_step(self, identifier, index, *, generation):
        with self.lock:
            run_index, run = self._run(identifier, generation)
            self.check(run['revision'], generation)
            if type(index) is not int or not 0 <= index < len(run['steps']): raise ValueError('Invalid scene step.')
            if run['steps'][index]['status'] != 'not_started': raise ValueError('This step cannot be replayed.')
            if any(step['status'] in ('not_started', 'unknown') for step in run['steps'][:index]):
                raise ValueError('Finish the preceding step first.')
            runs = deepcopy(self.runs)
            runs[run_index]['steps'][index]['status'] = 'unknown'
            self._save(runs=runs)
            return deepcopy(run['steps'][index]['action'])

    def finish_step(self, identifier, index, status, *, generation):
        if status not in OUTCOMES: raise ValueError('Invalid scene outcome.')
        with self.lock:
            run_index, run = self._run(identifier, generation)
            # Record an already dispatched command even if the owner disabled the
            # scene during I/O. This never authorizes a subsequent step.
            if (type(index) is not int or not 0 <= index < len(run['steps'])
                    or run['steps'][index]['status'] != 'unknown'):
                raise ValueError('This scene step is not awaiting an outcome.')
            runs = deepcopy(self.runs)
            runs[run_index]['steps'][index]['status'] = status
            self._save(runs=runs)

    def finish(self, identifier, *, generation, completed=True):
        if type(completed) is not bool: raise ValueError('Invalid scene completion.')
        with self.lock:
            run_index, _ = self._run(identifier, generation)
            runs = deepcopy(self.runs)
            # A stopped/expired run is terminal but not finished: untouched
            # actions must never be replayed, and the owner must see that the
            # sequence was interrupted even after a process restart.
            runs[run_index]['finished'] = completed
            self._save(runs=runs)
            self.active = None

    def configuration(self):
        with self.lock:
            history = deepcopy(self.runs)
            for run in history:
                run['interrupted'] = not run['finished'] and run['id'] != self.active
            return {'revision': self.revision, 'definitions': deepcopy(self.definitions), 'runs': history,
                    'busy': self.active is not None, 'recovery_error': self.recovery_error, 'remote_control': False}
