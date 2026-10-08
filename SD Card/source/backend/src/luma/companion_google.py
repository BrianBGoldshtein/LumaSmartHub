"""Optional web-client consent, bound to an enrolled live phone session.

No Desktop configuration/pending record is changed. Pending web attempts are
bounded RAM: API restart invalidates the ANCS generation, so consent must restart
as well. Tokens are committed only after complete consent and a fresh check.
"""
from __future__ import annotations

import json
import re
import secrets
from time import monotonic
from urllib.parse import parse_qs, urlsplit

from google_auth_oauthlib.flow import Flow

from .companion_auth import TOKEN, private_origin
from .integrations.google_calendar import CALENDAR_SCOPE, TASK_WRITE_SCOPE, TOKEN_KEY

WEB_CLIENT_KEY='companion_google_web_client_v1'
CALLBACK='/remote/google/callback'
AUTH_URI='https://accounts.google.com/o/oauth2/auth'
TOKEN_URI='https://oauth2.googleapis.com/token'


class CompanionGoogle:
    def __init__(self,auth,google,*,clock=monotonic,flow_factory=Flow.from_client_config,client_storage=None):
        self.auth,self.google,self.storage=auth,google,google.storage
        # Shared application registration is not a shared Google account.
        # Only tokens/pending consent belong to the selected account store.
        self.client_storage=client_storage if client_storage is not None else self.storage
        self.clock,self.flow_factory=clock,flow_factory
        self.pending={}
        self.consent_epoch=0

    def cancel_pending(self):
        # Includes consent already exchanging a code outside auth.lock: its
        # local row cannot commit tokens after a policy/setup invalidation.
        with self.auth.lock:
            self.consent_epoch+=1
            self.pending.clear()

    def status(self,origin):
        redirect=private_origin(origin)+CALLBACK
        try:
            config=json.loads(self.client_storage.get_secret(WEB_CLIENT_KEY) or 'null')
            configured=bool(config and redirect in config['web']['redirect_uris'])
        except (ValueError,TypeError,KeyError):configured=False
        return {'web_configured':configured,'redirect_uri':redirect}

    def set_client(self,payload,origin,recheck):
        redirect=private_origin(origin)+CALLBACK
        try:
            if not isinstance(payload,dict) or set(payload)!={'web'}:raise ValueError
            web=payload['web']
            if not isinstance(web,dict):raise ValueError
            client,secret,redirects=web['client_id'],web['client_secret'],web['redirect_uris']
            if not isinstance(client,str) or not re.fullmatch(r'[A-Za-z0-9._-]{10,240}\.apps\.googleusercontent\.com',client):raise ValueError
            if not isinstance(secret,str) or not 1<=len(secret)<=512 or any(ord(c)<33 or ord(c)==127 for c in secret):raise ValueError
            if not isinstance(redirects,list) or len(redirects)>20 or redirect not in redirects:raise ValueError
            if web.get('auth_uri',AUTH_URI)!=AUTH_URI or web.get('token_uri',TOKEN_URI)!=TOKEN_URI:raise ValueError
        except (ValueError,TypeError,KeyError):
            raise ValueError('Upload a Google Web application client with this exact HTTPS redirect URI.') from None
        # Normalize endpoints and redirect to prevent configuration-driven SSRF.
        config={'web':{'client_id':client,'client_secret':secret,'auth_uri':AUTH_URI,
                       'token_uri':TOKEN_URI,'redirect_uris':[redirect]}}
        with self.google._oauth_lock:
            with self.auth.lock:
                recheck()
                self.client_storage.set_secret(WEB_CLIENT_KEY,json.dumps(config,separators=(',',':')))
                self.cancel_pending()
        return self.status(origin)

    def begin(self,device,origin,identity,initial,*,task_updates=False):
        if type(task_updates) is not bool:raise ValueError('Choose read-only or task-update consent.')
        with self.google._oauth_lock:
            with self.auth.lock:
                self.auth.still_authorized(device,origin,identity,initial)
                if not self.status(origin)['web_configured']:raise ValueError('Configure the optional Google Web application client first.')
                config=json.loads(self.client_storage.get_secret(WEB_CLIENT_KEY))
                now=self.clock();self.pending={key:row for key,row in self.pending.items() if row['expires']>now}
                # Each browser gets one attempt, with at most eight attempts.
                self.pending={key:row for key,row in self.pending.items() if row['device']!=device}
                if len(self.pending)>=8:raise ValueError('Too many pending sign-ins. Try again later.')
                state,verifier=secrets.token_urlsafe(32),secrets.token_urlsafe(64)
                scopes=[CALENDAR_SCOPE]+([TASK_WRITE_SCOPE] if task_updates or self.google.task_write_authorized() else [])
                flow=self.flow_factory(config,scopes=scopes,state=state,code_verifier=verifier,autogenerate_code_verifier=False)
                flow.redirect_uri=origin+CALLBACK
                url,_=flow.authorization_url(access_type='offline',prompt='consent',include_granted_scopes='true')
                target=urlsplit(url)
                if target.scheme!='https' or target.netloc!='accounts.google.com' or len(url)>8192:raise ValueError('Google sign-in is unavailable.')
                self.pending[state]={'device':device,'origin':origin,'identity':identity,'initial':initial,
                    'verifier':verifier,'scopes':scopes,'config':config,'expires':now+900,
                    'consent_epoch':self.consent_epoch}
                return {'url':url,'expires_in_seconds':900}

    def finish(self,origin,identity,query):
        origin=private_origin(origin)
        if not isinstance(query,str) or len(query)>8192:raise ValueError('Sign-in did not finish.')
        try:
            params=parse_qs(query,keep_blank_values=True,max_num_fields=32)
            states=params.get('state',[]);codes=params.get('code',[])
            if len(states)!=1 or not TOKEN.fullmatch(states[0]):raise ValueError
        except (ValueError,TypeError):raise ValueError('Sign-in did not finish.') from None
        with self.google._oauth_lock:
            with self.auth.lock:
                row=self.pending.get(states[0])
                if not row or row['origin']!=origin or row['identity']!=identity:raise ValueError('Sign-in did not match.')
                # Consume before provider exchange, including denial/expiry.
                self.pending.pop(states[0])
                self.auth.still_authorized(row['device'],origin,identity,row['initial'])
                if self.clock()>=row['expires'] or 'error' in params or len(codes)!=1 or not 0<len(codes[0])<=4096:
                    raise ValueError('Sign-in expired or was canceled.')
            flow=self.flow_factory(row['config'],scopes=row['scopes'],state=states[0],code_verifier=row['verifier'],autogenerate_code_verifier=False)
            flow.redirect_uri=origin+CALLBACK;flow.oauth2session.trust_env=False
            flow.fetch_token(code=codes[0],timeout=15)
            credentials=flow.credentials
            granted=credentials.granted_scopes if credentials.granted_scopes is not None else credentials.scopes
            if not credentials.refresh_token or not set(row['scopes']).issubset(set(granted or [])):
                raise ValueError('Offline access and requested permissions are required.')
            saved=json.loads(credentials.to_json());saved['scopes']=list(granted or [])
            # Provider tokens never go to the browser. Serialize against token
            # refresh/Desktop consent; revoke/disconnect before commit wins.
            with self.auth.lock:
                self.auth.still_authorized(row['device'],origin,identity,row['initial'])
                if (row['consent_epoch']!=self.consent_epoch or self.clock()>=row['expires']
                        or json.loads(self.client_storage.get_secret(WEB_CLIENT_KEY) or 'null')!=row['config']):
                    raise ValueError('Sign-in expired or configuration changed.')
                self.storage.set_secret(TOKEN_KEY,json.dumps(saved))
