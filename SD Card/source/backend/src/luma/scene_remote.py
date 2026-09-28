"""Separate owner-consented, exact-action allowlist for private remote scenes."""
from copy import deepcopy
from uuid import uuid4

from .scene_devices import digest
from .scenes import SCENES, uuid


class RemoteScenePolicy:
    """Persist only scene/action fingerprints; never infer grants from scenes.

    A grant applies only to the exact ordered, device-bound actions reviewed at
    consent time. Editing, relinking or reordering actions makes the grant stale
    until the owner reviews and saves the remote allowlist again.
    """
    def __init__(self, storage):
        self.storage = storage
        self.revision = str(uuid4())
        self.enabled = False
        self.grants = {}
        self.recovery_error = False
        try:
            raw = storage.get_cache('room', 'scene_remote_policy')
            if raw is not None:
                self.validate(raw)
                self.revision, self.enabled, self.grants = raw['revision'], raw['enabled'], raw['grants']
        except Exception:
            self.recovery_error = True

    @staticmethod
    def validate(raw):
        if (not isinstance(raw, dict) or set(raw) != {'version','revision','enabled','grants'}
                or type(raw['version']) is not int or raw['version'] != 1
                or type(raw['enabled']) is not bool or not isinstance(raw['grants'], dict)
                or set(raw['grants']) - set(SCENES)):
            raise ValueError('Invalid remote scene permissions.')
        uuid(raw['revision'])
        for key, value in raw['grants'].items():
            if (not isinstance(value, str) or len(value) != 64
                    or any(char not in '0123456789abcdef' for char in value)):
                raise ValueError('Invalid remote scene permissions.')

    def check(self, revision):
        if self.recovery_error:
            raise ValueError('Remote scene permissions need recovery. Nothing was overwritten.')
        if revision != self.revision:
            raise ValueError('Remote permissions changed. Reload and review again.')

    def effective(self, key, definition):
        if self.recovery_error or not self.enabled or key not in self.grants:
            return False
        actions = definition.get('actions') if isinstance(definition, dict) else None
        return bool(definition.get('enabled') and actions and self.grants[key] == digest(actions))

    def configuration(self, definitions):
        return {'revision': self.revision, 'enabled': self.enabled,
                'recovery_error': self.recovery_error,
                'scenes': {key: {'allowed': self.effective(key, definitions[key]),
                                 'needs_review': key in self.grants and not self.effective(key, definitions[key])}
                           for key in SCENES}}

    def save(self, enabled, keys, *, revision, definitions, devices):
        if type(enabled) is not bool or not isinstance(keys, list) or len(keys) > len(SCENES):
            raise ValueError('Review the remote scene choices again.')
        if len(set(keys)) != len(keys) or any(key not in SCENES for key in keys):
            raise ValueError('Choose each supported scene at most once.')
        if enabled != bool(keys):
            raise ValueError('Turn remote scene access off, or choose at least one exact scene.')
        self.check(revision)
        grants = {}
        for key in keys:
            definition = definitions[key]
            if not definition['enabled'] or not definition['actions']:
                raise ValueError('Only configured, enabled scenes can be remotely allowed.')
            # Recheck all selected action/device capabilities at consent time.
            devices.bind(definition['actions'])
            grants[key] = digest(definition['actions'])
        raw = {'version': 1, 'revision': str(uuid4()), 'enabled': enabled, 'grants': grants}
        self.validate(raw)
        self.storage.set_cache('room', 'scene_remote_policy', raw)
        self.revision, self.enabled, self.grants = raw['revision'], enabled, deepcopy(grants)

    def reset_corrupt(self, *, revision, confirmed):
        if not self.recovery_error or confirmed is not True or revision != self.revision:
            raise ValueError('Confirm the exact remote-permission reset shown on screen.')
        raw = {'version': 1, 'revision': str(uuid4()), 'enabled': False, 'grants': {}}
        self.validate(raw)
        self.storage.set_cache('room', 'scene_remote_policy', raw)
        self.revision, self.enabled, self.grants, self.recovery_error = raw['revision'], False, {}, False
