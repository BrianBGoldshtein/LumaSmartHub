"""Short, RAM-only primary administration; presence is not a settings PIN."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import secrets
from threading import RLock
from time import monotonic

from .security import SecurityManager, PIN_SECRET_KEY

COOKIE = 'luma_primary_admin'
LEASE_SECONDS = 300
FRESH_SECONDS = 60
MAX_LEASES = 32
GLOBAL_COMMANDS = frozenset({'set_brightness', 'set_volume', 'set_theme', 'set_orientation',
                             'run_scene', 'cancel_scene', 'run_remote_scene'})
COMMAND_PATHS = frozenset({'/api/v1/commands', '/api/v1/voice/command', '/api/v1/shortcut-command'})
PUBLIC_WRITES = frozenset({
    '/api/v1/admin/unlock', '/api/v1/admin/lock', '/api/v1/security/unlock',
    # These two existing local controllers validate a fresh primary PIN on
    # every operation themselves; a separate cookie would duplicate that gate.
    '/api/v1/network/hotspot', '/api/v1/bluetooth/forget',
    '/api/v1/companion/local', '/api/v1/companion/protocol', '/api/v1/companion/dispatch',
    '/api/v1/companion/google-callback', '/api/v1/todos/complete', '/api/v1/departures/action',
    '/api/v1/display/frame', '/api/v1/device/report', '/api/v1/device/keyboard',
    '/api/v1/device/display-register', '/api/v1/device/display-claim', '/api/v1/device/display-confirm',
    '/api/v1/device/timer-chime', '/api/v1/device/notification-chime',
    '/api/v1/voice/phase', '/api/v1/voice/diagnostic', '/api/v1/voice/heartbeat',
    '/api/v1/voice/output-report', '/api/v1/voice/calibration/level', '/api/v1/voice/calibration/sample',
    '/api/v1/voice/call-trial/armed', '/api/v1/voice/call-trial/observation',
    '/api/v1/voice/speaker-trial/armed', '/api/v1/voice/speaker-trial/observation',
    '/api/v1/voice/asset/preview/result', '/api/v1/voice/asset/tone/result',
})
PRIVATE_READS = frozenset({'/api/v1/settings', '/api/v1/onboarding', '/api/v1/bluetooth/pairing',
    '/api/v1/users',
    '/api/v1/google/status', '/api/v1/google/calendars', '/api/v1/google/event-colors',
    '/api/v1/security/lan-token', '/api/v1/diagnostics', '/api/v1/countdowns',
    '/api/v1/transit', '/api/v1/room', '/api/v1/scenes', '/api/v1/backups/media'})
FRESH_PATHS = frozenset({'/api/v1/updates/install', '/api/v1/backups/apply',
                         '/api/v1/users/manage',
                         '/api/v1/security/pin', '/api/v1/security/lan-token/rotate'})


def needs_admin(method: str, path: str, command: str | None = None) -> bool:
    from .user_setup import SELF_WRITES
    if path in SELF_WRITES:
        return False  # Each fixed route requires the own-account wall grant.
    if path in COMMAND_PATHS:
        return command in GLOBAL_COMMANDS
    if method in {'GET', 'HEAD'}:
        return path in PRIVATE_READS
    # New management mutations are protected by default. Device reports and
    # delegated account APIs need an explicit, reviewed exception instead.
    return method in {'POST', 'PATCH', 'PUT', 'DELETE'} and path.startswith('/api/v1/') and path not in PUBLIC_WRITES


class AdminDenied(Exception):
    def __init__(self, *, fresh=False):
        super().__init__('Confirm your primary PIN again.' if fresh else 'Unlock primary settings with your hub PIN.')
        self.fresh = fresh


@dataclass(frozen=True)
class Lease:
    audience: str
    pin_revision: str
    started: float
    presence: object = None


class AdminAuthority:
    def __init__(self, storage, *, clock=monotonic):
        self.storage, self.clock = storage, clock
        self.security = SecurityManager(storage)
        self.lock = RLock()
        self.leases: dict[str, Lease] = {}

    def _revision(self):
        return hashlib.sha256((self.storage.get_secret(PIN_SECRET_KEY) or '').encode()).hexdigest()

    def _pin(self, pin):
        if not isinstance(pin, str) or not self.security.verify_pin(pin):
            raise AdminDenied()

    def _save(self, key, audience, presence=None):
        now = self.clock()
        self.leases = {key: row for key, row in self.leases.items() if now-row.started < LEASE_SECONDS}
        if key not in self.leases and len(self.leases) >= MAX_LEASES:
            raise AdminDenied()
        self.leases[key] = Lease(audience, self._revision(), now, presence)

    def _require(self, key, audience, *, fresh=False, presence=None):
        row = self.leases.get(key)
        if (row is None or row.audience != audience or row.pin_revision != self._revision()
                or row.presence != presence or not 0 <= self.clock()-row.started < LEASE_SECONDS):
            self.leases.pop(key, None)
            raise AdminDenied()
        if fresh and self.clock()-row.started >= FRESH_SECONDS:
            raise AdminDenied(fresh=True)
        return max(0, int(LEASE_SECONDS-(self.clock()-row.started)))

    @staticmethod
    def _local_key(token):
        if not isinstance(token, str) or len(token) != 43:
            raise AdminDenied()
        return 'wall:'+hashlib.sha256(token.encode()).hexdigest()

    def unlock_local(self, pin, origin, *, previous=None):
        with self.lock:
            self._pin(pin)
            token = secrets.token_urlsafe(32)
            if previous:
                self.lock_local(previous)
            self._save(self._local_key(token), origin)
            return token

    def require_local(self, token, origin, *, fresh=False):
        with self.lock:
            return self._require(self._local_key(token), origin, fresh=fresh)

    def lock_local(self, token):
        with self.lock:
            try:
                self.leases.pop(self._local_key(token), None)
            except AdminDenied:
                pass

    @staticmethod
    def _primary(presence):
        if not (presence.authorized and presence.profile_id == 'primary' and presence.role == 'primary'):
            raise AdminDenied()

    def unlock_remote(self, pin, device, presence):
        with self.lock:
            self._primary(presence)  # Guest PIN possession cannot promote a grant.
            self._pin(pin)
            self._save('remote:'+device, 'primary-remote', presence)

    def require_remote(self, device, presence, *, fresh=False):
        with self.lock:
            self._primary(presence)
            return self._require('remote:'+device, 'primary-remote', presence=presence, fresh=fresh)

    def lock_remote(self, device):
        with self.lock:
            self.leases.pop('remote:'+device, None)

    def clear(self):
        with self.lock:
            self.leases.clear()
