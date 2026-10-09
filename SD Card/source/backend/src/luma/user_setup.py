"""Primary-approved local personal setup; never authority by profile ID alone.

The wall cookie is HttpOnly and its hashed, origin/phone-bound grant survives an
application restart. A draft may only pair for one hour; a bound grant permits
its own personal controls for 30 days, and only with live ANCS authorization.
Backup restore, replacing a phone, and removing a profile revoke these grants.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
import re
import secrets
from threading import RLock

from .pairing import PairingFlow
from .profiles import PRIMARY_ID, ProfileError, personal_settings, phone_address

COOKIE = 'luma_personal_setup'
GRANT_KEY = 'wall_setup_grant_v1'
TOKEN = re.compile(r'[A-Za-z0-9_-]{43}\Z')
DRAFT_SECONDS = 3600
BOUND_SECONDS = 30 * 86400
SELF_WRITES = frozenset({f'/api/v1/user-self/{path}' for path in (
    'progress', 'settings', 'pairing/start', 'pairing/select', 'pairing/confirm', 'pairing/cancel',
    'google/authorize', 'google/sync', 'todos/complete', 'timer', 'lock',
    'remote/issue', 'remote/approve',
)})


class SetupDenied(PermissionError):
    def __init__(self):
        super().__init__('Ask the primary user to open your personal setup, then connect your authorized iPhone.')


class UserSetup:
    def __init__(self, app, *, clock=lambda: datetime.now(UTC)):
        self.app, self.profiles, self.clock = app, app.state.profiles, clock
        self.lock = RLock()
        self.pairing = PairingFlow(self._save_phone, validate_phone=self._validate_phone)
        self.pairing_owner = None
        self.desktop = None

    @staticmethod
    def _digest(token):
        if not isinstance(token, str) or not TOKEN.fullmatch(token):
            raise SetupDenied()
        return hashlib.sha256(token.encode()).hexdigest()

    def _key(self, uid):
        return GRANT_KEY if uid == PRIMARY_ID else f'profile:{uid}:{GRANT_KEY}'

    def issue(self, uid, origin):
        """Only an already verified primary administrator calls this method."""
        with self.lock:
            user = self.profiles.get(uid)
            if self.pairing_active() and self.pairing_owner and self.pairing_owner[2] == uid:
                raise ProfileError('Finish or cancel this user’s pairing before opening setup again.')
            token = secrets.token_urlsafe(32)
            ttl = BOUND_SECONDS if user.phone_address else DRAFT_SECONDS
            row = {'digest': self._digest(token), 'origin': origin, 'phone': user.phone_address,
                   'expires': (self.clock()+timedelta(seconds=ttl)).isoformat()}
            self.profiles.account_storage(uid).set_secret(GRANT_KEY, json.dumps(row, separators=(',', ':')))
            if self.desktop:
                self.desktop.cancel(uid)
            return token, ttl

    def require(self, token, origin, *, allow_draft=False, initial=None):
        with self.lock:
            digest = self._digest(token)
            for user in self.profiles.list():
                encoded = self.profiles.account_storage(user.id).get_secret(GRANT_KEY)
                try:
                    row = json.loads(encoded or 'null')
                    if (not isinstance(row, dict) or set(row) != {'digest','origin','phone','expires'}
                            or not isinstance(row['digest'], str) or not secrets.compare_digest(row['digest'], digest)):
                        continue
                    expires = datetime.fromisoformat(row['expires'])
                    if (row['origin'] != origin or row['phone'] != user.phone_address or expires.tzinfo is None
                            or not self.clock() < expires <= self.clock()+timedelta(seconds=BOUND_SECONDS)):
                        raise SetupDenied()
                    if not user.phone_address:
                        if not allow_draft or initial is not None:
                            raise SetupDenied()
                        return user, None
                    phone = self.app.state.bluetooth.companion_presence(user.id)
                    if (not phone.authorized or phone.address != user.phone_address or not phone.generation
                            or (initial is not None and phone != initial)):
                        raise SetupDenied()
                    return user, phone
                except (ValueError, TypeError, KeyError):
                    raise SetupDenied() from None
            raise SetupDenied()

    def recheck(self, token, origin, *, allow_draft=False):
        user, initial = self.require(token, origin, allow_draft=allow_draft)
        def check():
            current, _ = self.require(token, origin, allow_draft=allow_draft, initial=initial)
            if current.id != user.id:
                raise SetupDenied()
        return user, check

    def validate_commit(self, db, uid, token, origin, initial):
        """Check binding/grant inside the same write transaction as credentials.

        Even a legacy primary route using another thread cannot revoke the
        grant between this check and token commit. No transaction crosses I/O.
        """
        user = self.profiles._find(self.profiles._read(db), uid)
        address = phone_address(self.profiles._legacy(db).phone_address if uid == PRIMARY_ID else user['phone_address'])
        saved = db.execute('SELECT payload FROM secrets WHERE key=?', (self._key(uid),)).fetchone()
        try:
            row = json.loads(saved[0] if saved else 'null')
            if (not isinstance(row, dict) or row['digest'] != self._digest(token) or row['origin'] != origin
                    or not address or row['phone'] != address or self.clock() >= datetime.fromisoformat(row['expires'])
                    or self.app.state.bluetooth.companion_presence(uid) != initial or not initial.authorized):
                raise SetupDenied()
        except (ValueError, TypeError, KeyError):
            raise SetupDenied() from None

    def invalidate(self, uid):
        """Call under the companion lock after profile lifetime/binding changes."""
        auth = self.app.state.companion
        auth._clear_profile(uid)
        web = self.app.state.companion_google_accounts.get(uid)
        if web:
            web.cancel_pending()
        if self.desktop:
            self.desktop.cancel(uid)
        child = self.app.state.bluetooth.children.get(uid)
        if child:
            child.remote_authorized.clear()
            child.service.phone_disconnected()
        if uid == PRIMARY_ID:
            self.app.state.luma.machine.settings = self.profiles.storage.load_settings()
        self.app.state.luma.publish('user.registration.updated', {'profile_id': uid})

    def revoke(self, uid):
        with self.profiles.storage.transaction() as db:
            db.execute('DELETE FROM secrets WHERE key=?', (self._key(uid),))
        if self.desktop:
            self.desktop.cancel(uid)

    def pairing_active(self):
        return bool(self.pairing.task and not self.pairing.task.done())

    def start_pairing(self, token, origin):
        with self.lock:
            user, _ = self.require(token, origin, allow_draft=True)
            if user.phone_address:
                raise ProfileError('Ask the primary user to change an existing phone registration.')
            legacy = self.app.state.pairing
            if (legacy.task and not legacy.task.done()) or self.pairing_active():
                raise ProfileError('Finish or cancel the other pairing session first.')
            self.pairing_owner = (token, origin, user.id)
            return self.pairing.start()

    def _validate_phone(self, address):
        if not self.pairing_owner:
            raise SetupDenied()
        token, origin, uid = self.pairing_owner
        user, _ = self.require(token, origin, allow_draft=True)
        if user.id != uid or user.phone_address or self.profiles.by_phone(address):
            raise ProfileError('Choose a phone that is not registered to another user.')

    def _save_phone(self, address):
        with self.lock, self.app.state.companion.lock:
            self._validate_phone(address)
            token, origin, uid = self.pairing_owner
            self.profiles.bind_phone(uid, address)
            if uid == PRIMARY_ID:
                self.profiles.set_setup(uid, 'remote')
            self.invalidate(uid)
            # The draft approval becomes a phone-bound personal grant. Existing
            # grants were revoked by bind_phone; no old phone grant is reused.
            self.profiles.account_storage(uid).set_secret(GRANT_KEY, json.dumps({
                'digest': self._digest(token), 'origin': origin, 'phone': self.profiles.get(uid).phone_address,
                'expires': (self.clock()+timedelta(seconds=BOUND_SECONDS)).isoformat()}, separators=(',', ':')))

    def pairing_snapshot(self, uid):
        if self.pairing_owner and self.pairing_owner[2] == uid:
            result = self.pairing.snapshot()
            result['devices'] = [row for row in result['devices'] if self.profiles.by_phone(row['address']) is None]
            return result
        return {'session':None, 'phase':'idle', 'devices':[], 'selected':None,
                'challenge':None, 'passkey':None, 'message':''}

    def view(self, uid):
        user = self.profiles.get(uid)
        child = self.app.state.bluetooth.children.get(uid)
        account = self.app.state.profile_calendars.account(uid)
        authorized = self.app.state.bluetooth.companion_presence(uid).authorized
        return {'profile_id':uid, 'nickname':user.nickname, 'role':user.role,
                'setup_stage':user.setup_stage, 'wall_share_approved':user.wall_share_approved,
                'phone_registered':bool(user.phone_address),
                'phone_authorized':authorized,
                'connection_status':child.status if child else 'Choose your iPhone',
                'remote_allowed':self.profiles.remote_allowed(uid),
                'google':{'configured':self.desktop.configured() if self.desktop else account.google.configured(),
                          'authorized':authorized and account.google.authorized(),
                          'task_updates':authorized and account.google.task_write_authorized(),
                          **(account.status if authorized else {})},
                'personal':user.personal if authorized else personal_settings({}),
                'theme':self.app.state.luma.settings.theme.value,
                'pairing':self.pairing_snapshot(uid)}
