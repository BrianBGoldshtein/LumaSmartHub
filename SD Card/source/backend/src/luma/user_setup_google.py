"""Local Desktop consent with PKCE and a delegated own-account commit guard."""
from __future__ import annotations

import json
import re
import secrets
from time import monotonic
from urllib.parse import parse_qs, urlsplit

from google_auth_oauthlib.flow import Flow

from .companion_google import AUTH_URI, TOKEN_URI
from .integrations.google_calendar import CALENDAR_SCOPE, TASK_WRITE_SCOPE, CLIENT_CONFIG_KEY, TOKEN_KEY

CALLBACK = 'http://127.0.0.1:8742/api/v1/user-self/google/callback'


class UserSetupGoogle:
    def __init__(self, setup, *, clock=monotonic, flow_factory=Flow.from_client_config):
        self.setup, self.clock, self.flow_factory = setup, clock, flow_factory
        self.pending = {}
        self.epochs = {}

    def _config(self):
        try:
            config = json.loads(self.setup.profiles.storage.get_secret(CLIENT_CONFIG_KEY) or 'null')
            client = config['installed']
            if (not isinstance(client['client_id'], str) or
                    not re.fullmatch(r'[A-Za-z0-9._-]{10,240}\.apps\.googleusercontent\.com', client['client_id'])
                    or not isinstance(client['client_secret'], str) or not 1 <= len(client['client_secret']) <= 512
                    or any(ord(c) < 33 or ord(c) == 127 for c in client['client_secret'])
                    or client.get('auth_uri', AUTH_URI) != AUTH_URI or client.get('token_uri', TOKEN_URI) != TOKEN_URI):
                raise ValueError
            return {'installed':{'client_id':client['client_id'], 'client_secret':client['client_secret'],
                    'auth_uri':AUTH_URI, 'token_uri':TOKEN_URI, 'redirect_uris':[CALLBACK]}}
        except (ValueError, TypeError, KeyError):
            raise ValueError('Ask the primary user to configure a Google Desktop application client first.') from None

    def configured(self):
        try:
            self._config()
            return True
        except ValueError:
            return False

    def cancel(self, uid):
        with self.setup.lock:
            self.epochs[uid] = self.epochs.get(uid, 0)+1
            self.pending = {key:row for key,row in self.pending.items() if row['uid'] != uid}
            # Deleted profile IDs cannot grow the RAM cancellation map forever.
            live = {user.id for user in self.setup.profiles.list()}
            self.epochs = {key:value for key,value in self.epochs.items() if key in live}

    def begin(self, token, origin, *, task_updates=False):
        if type(task_updates) is not bool:
            raise ValueError('Choose read-only or task-update consent.')
        if origin != 'http://127.0.0.1:8742':
            raise ValueError('Open Luma at http://127.0.0.1:8742 on this Pi before starting local Google sign-in.')
        with self.setup.lock:
            user, initial = self.setup.require(token, origin)
            account = self.setup.app.state.profile_calendars.account(user.id)
            config = self._config()
            self.cancel(user.id)
            now = self.clock()
            self.pending = {key:row for key,row in self.pending.items() if now < row['expires']}
            state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
            scopes = [CALENDAR_SCOPE]+([TASK_WRITE_SCOPE] if task_updates or account.google.task_write_authorized() else [])
            flow = self.flow_factory(config, scopes=scopes, state=state,
                                     code_verifier=verifier, autogenerate_code_verifier=False)
            flow.redirect_uri = CALLBACK
            url, _ = flow.authorization_url(access_type='offline', prompt='consent', include_granted_scopes='true')
            target = urlsplit(url)
            if target.scheme != 'https' or target.netloc != 'accounts.google.com' or len(url) > 8192:
                raise ValueError('Google sign-in is unavailable.')
            self.pending[state] = {'uid':user.id, 'token':token, 'origin':origin, 'initial':initial,
                'config':config, 'verifier':verifier, 'scopes':scopes, 'expires':now+900,
                'epoch':self.epochs.get(user.id, 0)}
            return {'url':url, 'expires_in_seconds':900}

    def finish(self, token, origin, query):
        if not isinstance(query, str) or len(query) > 8192:
            raise ValueError('Sign-in did not finish.')
        params = parse_qs(query, keep_blank_values=True, max_num_fields=32)
        states, codes = params.get('state', []), params.get('code', [])
        if len(states) != 1 or not re.fullmatch(r'[A-Za-z0-9_-]{43}', states[0]):
            raise ValueError('Sign-in did not match.')
        with self.setup.lock:
            row = self.pending.get(states[0])
            if not row or row['token'] != token or row['origin'] != origin:
                raise ValueError('Sign-in did not match.')
            self.pending.pop(states[0])  # One use, before any provider exchange.
            user, _ = self.setup.require(token, origin, initial=row['initial'])
            if (user.id != row['uid'] or self.clock() >= row['expires'] or 'error' in params
                    or len(codes) != 1 or not 0 < len(codes[0]) <= 4096):
                raise ValueError('Sign-in expired or was canceled.')
            account = self.setup.app.state.profile_calendars.account(user.id)
        # Never hold the setup lock across network I/O; removal/revocation must
        # be able to win. The existing OAuth lock serializes this user's tokens.
        with account.google._oauth_lock:
            flow = self.flow_factory(row['config'], scopes=row['scopes'], state=states[0],
                                     code_verifier=row['verifier'], autogenerate_code_verifier=False)
            flow.redirect_uri = CALLBACK
            flow.oauth2session.trust_env = False
            flow.fetch_token(code=codes[0], timeout=15)
            credentials = flow.credentials
            granted = credentials.granted_scopes if credentials.granted_scopes is not None else credentials.scopes
            if not credentials.refresh_token or not set(row['scopes']).issubset(set(granted or [])):
                raise ValueError('Offline access and requested permissions are required.')
            saved = json.loads(credentials.to_json())
            saved['scopes'] = list(granted or [])
            with self.setup.lock:
                self.setup.require(token, origin, initial=row['initial'])
                if (self.clock() >= row['expires'] or self.epochs.get(user.id, 0) != row['epoch']
                        or self._config() != row['config']):
                    raise ValueError('Sign-in expired or setup changed.')
                # Lifetime check plus both writes are one transaction. Removal
                # cannot create an orphaned credential after this check.
                with self.setup.profiles.storage.transaction() as db:
                    self.setup.validate_commit(db, user.id, token, origin, row['initial'])
                    if self._config() != row['config']:
                        raise ValueError('Google application configuration changed.')
                    for key, value in ((TOKEN_KEY, saved), (CLIENT_CONFIG_KEY, row['config'])):
                        actual = key if user.primary else f'profile:{user.id}:{key}'
                        db.execute("INSERT INTO secrets(key,payload,updated_at) VALUES(?,?,datetime('now')) "
                            "ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
                            (actual, json.dumps(value, separators=(',', ':'))))
                account.status.update(error=None, error_kind=None, reconnect_required=False)
                self.setup.app.state.luma.publish('user.google.connected', {'profile_id': user.id})
