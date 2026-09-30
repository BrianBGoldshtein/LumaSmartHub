"""Server-minted bindings and guarded dispatch through existing device locks."""
from copy import deepcopy
import hashlib
import json

from .purifier_adapter import PurifierBusy, PurifierRateLimit, PurifierUnavailable


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class SceneDevices:
    def __init__(self, service, room, *, utcnow):
        self.service, self.room, self.utcnow = service, room, utcnow

    def binding(self, device):
        if device == 'purifier':
            store = self.service.room
            if store.recovery_error or store.selected is None or store.session is None: return None
            return digest(['purifier', store.revision, store.selected['id']])
        return None

    def overridden(self, device):
        return device == 'purifier' and self.service.room.override_active(self.utcnow())

    def supported(self, item):
        device, key, value = item['device'], item['action'], item['value']
        if item['binding'] != self.binding(device): return False
        if device == 'purifier':
            view = self.service.room.view(self.utcnow())
            caps = view['capabilities'] if view and view['fresh'] else None
            if not caps: return False
            if key in ('power', 'display'): return type(value) is bool and caps.get(key) is True
            if key == 'speed': return type(value) is int and value in caps.get('speeds', [])
            if key == 'mode': return type(value) is str and value in caps.get('modes', [])
            return False
        return False

    def catalog(self):
        rows = []
        store = self.service.room
        if store.selected:
            candidates = [('power', False, 'Off'), ('power', True, 'On'),
                          *[('speed', speed, f'Speed {speed} · turns on') for speed in (1, 2, 3)],
                          *[('mode', mode, f'{mode.title()} mode · may turn on') for mode in ('manual', 'sleep', 'auto')],
                          ('display', False, 'Display off'), ('display', True, 'Display on')]
            rows.append(self._catalog_device('purifier', store.selected['name'], candidates))
        return rows

    def _catalog_device(self, device, name, candidates):
        actions = []
        for key, value, label in candidates:
            item = {'device': device, 'action': key, 'value': value, 'binding': self.binding(device)}
            if self.supported(item): actions.append({**item, 'label': label})
        return {'id': device, 'name': name, 'actions': actions, 'override_active': self.overridden(device)}

    def bind(self, choices):
        """Require the editor's reviewed binding to still match; never auto-relink."""
        clean = []
        for item in choices:
            if not self.supported(item):
                raise ValueError('Device configuration or checks changed. Review its available actions again.')
            clean.append(deepcopy(item))
        return clean

    async def dispatch(self, item, *, can_send):
        device = item['device']
        if can_send() is not True: return 'not_sent'
        if self.overridden(device): return 'skipped_override'
        if not self.supported(item): return 'unavailable'
        guard = lambda: (can_send() is True and item['binding'] == self.binding(device)
                         and not self.overridden(device) and self.supported(item))
        try:
            if device == 'purifier':
                result = await self.room.scene_command(item['action'], item['value'], self.service.room.revision, can_send=guard)
                return {'confirmed': 'confirmed', 'unconfirmed': 'unconfirmed',
                        'rejected': 'rejected', 'not_sent': 'not_sent'}[result['status']]
        except (PurifierBusy, PurifierRateLimit): return 'unavailable'
        except (PurifierUnavailable, ValueError):
            # Transport may have crossed the physical boundary; receipts, not an
            # exception class, determine whether the outcome is known.
            return 'unconfirmed'
