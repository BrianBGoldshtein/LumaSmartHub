"""Primary-only shared settings transport. Never a caller-selected HTTP proxy.

Both screens use the same local validators. Each operation carries a live
browser/presence/PIN check in ASGI scope; personal setup cookies stay server-side.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
import json
import re

import httpx
from fastapi import HTTPException

from .admin_authority import AdminDenied, FRESH_PATHS
from .user_setup import COOKIE

READS = frozenset('''settings security/status security/lan-token onboarding users diagnostics
network/status network/hotspot bluetooth/pairing device/temperature device/fan
voice/hardware voice/calibration voice/library voice/asset voice/keyword-asset
voice/call-trial voice/speaker-trial countdowns transit room scenes backups/media
updates/status user-self/status user-self/google/calendars user-self/google/colors
user-self/remote/pending'''.split())
POSTS = frozenset('''onboarding security/pin security/unlock security/lan-token/rotate users/manage
network network/portal network/hotspot tailscale pi-connect device/fan companion/local
bluetooth/forget bluetooth/pairing/start bluetooth/pairing/select bluetooth/pairing/confirm
bluetooth/pairing/cancel voice/hardware/gain voice/calibration/start voice/calibration/cancel
voice/calibration/finish-wake-only voice/calibration/confirm-correction voice/calibration/save-audio
voice/adaptations/reset voice/wake-confirmation voice/audio-profile/reset voice/phrase-preview
voice/asset/retry voice/asset/repair voice/asset/preview voice/asset/tone
voice/keyword-asset/prepare voice/keyword-asset/repair voice/call-trial/start voice/call-trial/stop
voice/speaker-trial/model/install voice/speaker-trial/start voice/speaker-trial/begin
voice/speaker-trial/cancel countdowns/manual countdowns/search countdowns/google countdowns/refresh
transit/token transit/directory transit/favorites transit/preview transit/refresh transit/visible
room/vesync/login room/vesync/disconnect room/purifier/discover room/purifier/select
room/purifier/refresh room/purifier/command scenes/cancel scenes/remote/reset
backups/scan backups/export backups/preview backups/apply backups/eject updates/check updates/install
user-self/progress user-self/pairing/start user-self/pairing/select user-self/pairing/confirm
user-self/pairing/cancel user-self/lock user-self/remote/issue user-self/remote/approve
user-self/google/sync'''.split())
# These disrupt access, change secrets, export private configuration or restore
# state. Explicit owner confirmation is additional to existing controller PINs.
CONFIRM = frozenset('''security/pin security/lan-token/rotate users/manage network network/hotspot
tailscale bluetooth/forget backups/export backups/apply updates/install'''.split())
UUID = r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'


def needs_confirmation(operation):
    route = operation['path'].removeprefix('/api/v1/')
    if operation['method'] == 'GET' or route not in CONFIRM:
        return False
    if route == 'tailscale' and operation['body'].get('action') == 'status':
        return False
    if route == 'network' and operation['body'].get('action') in {'scan', 'check'}:
        return False
    return True


def validate_operations(payload):
    if not isinstance(payload, dict) or set(payload) != {'operations'}:
        raise HTTPException(422, 'Settings request is invalid.')
    operations = payload['operations']
    if not isinstance(operations, list) or not 1 <= len(operations) <= 12:
        raise HTTPException(422, 'Settings request is invalid.')
    result = []
    for operation in operations:
        if not isinstance(operation, dict) or set(operation) != {'method', 'path', 'body', 'confirmed'}:
            raise HTTPException(422, 'Settings request is invalid.')
        method, path = operation['method'], operation['path']
        if (not isinstance(method, str) or not isinstance(path, str)
                or not path.startswith('/api/v1/') or type(operation['confirmed']) is not bool
                or not isinstance(operation['body'], dict)):
            raise HTTPException(422, 'Settings request is invalid.')
        route = path.removeprefix('/api/v1/')
        allowed = (method == 'GET' and route in READS or method == 'POST' and route in POSTS
            or method == 'PATCH' and route in {'settings', 'user-self/settings'}
            or method == 'PATCH' and re.fullmatch(f'countdowns/{UUID}/visibility', route)
            or method == 'DELETE' and re.fullmatch(f'(countdowns|transit/favorites)/{UUID}', route)
            or method == 'PUT' and route in {'scenes/remote', 'scenes/morning', 'scenes/night', 'scenes/arrive', 'scenes/away'}
            or method == 'POST' and route in {'scenes/morning/run', 'scenes/night/run', 'scenes/arrive/run', 'scenes/away/run'})
        if not allowed or method == 'GET' and operation['body'] or len(operations) > 1 and method != 'GET':
            raise HTTPException(422, 'This settings operation is not available.')
        if needs_confirmation(operation) and not operation['confirmed']:
            raise HTTPException(409, 'Review and confirm this settings change first.')
        result.append(operation)
    return result


class PrimarySettings:
    def __init__(self, app):
        self.app = app
        self.cookies = OrderedDict()
        self.locks = {}  # At most eight approved browsers; pruned with cookies.

    async def dispatch(self, device, payload, check):
        operations = validate_operations(payload)
        check(fresh=False)
        if device not in self.locks:
            if len(self.locks) >= 16:
                raise HTTPException(503, 'Close other settings sessions and restart Luma.')
            self.locks[device] = asyncio.Lock()
        async with self.locks[device]:
            results = []
            for operation in operations:
                path, method = operation['path'], operation['method']
                fresh = path in FRESH_PATHS or needs_confirmation(operation)
                guard = lambda: check(fresh=fresh)
                guard()
                body = operation['body']
                if path == '/api/v1/backups/export':
                    # Game saves belong to the wall browser, not this iPhone.
                    body = {**body, 'games': await self.app.state.game_handoff.capture(guard)}

                async def guarded(scope, receive, send):
                    guard()
                    await self.app({**scope, 'luma_companion_check': guard, 'luma_admin_check': guard}, receive, send)

                headers = {'Content-Type': 'application/json'}
                cookie = self.cookies.get(device)
                if path.startswith('/api/v1/user-self/') and cookie:
                    headers['Cookie'] = COOKIE + '=' + cookie
                async with asyncio.timeout(45):
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=guarded, client=('127.0.0.1', 0)),
                            base_url='http://127.0.0.1:8742', trust_env=False, follow_redirects=False) as client:
                        response = await client.request(method, path, json=body if method != 'GET' else None, headers=headers)
                if len(response.content) > 1024 * 1024:
                    raise HTTPException(503, 'Settings response is too large.')
                value = response.json()
                if response.status_code == 403 and isinstance(value, dict) and value.get('code') == 'admin_required':
                    raise AdminDenied(fresh=value.get('fresh') is True)
                # PIN rotation deliberately ends the existing administrator lease.
                if not (path == '/api/v1/security/pin' and response.is_success):
                    check(fresh=False)
                if response.is_success:
                    if path == '/api/v1/users/manage':
                        new_cookie = response.cookies.get(COOKIE)
                        if new_cookie:
                            self.cookies[device] = new_cookie
                            self.cookies.move_to_end(device)
                            while len(self.cookies) > 8:
                                self.cookies.popitem(last=False)
                    if path == '/api/v1/user-self/lock':
                        self.cookies.pop(device, None)
                    if path == '/api/v1/backups/apply':
                        try:
                            await self.app.state.game_handoff.restore(value['games'], guard)
                            value['wall_games_restored'] = True
                        except (HTTPException, TimeoutError):
                            value['wall_games_restored'] = False
                    results.append({'status': response.status_code, 'body': value})
                else:
                    # No provider/validation input (credentials!) is reflected.
                    status = response.status_code if response.status_code in {403, 409, 410, 422, 429, 503} else 503
                    results.append({'status': status, 'body': {'detail': 'This step could not finish. Check the entered values and device status; saved settings are unchanged unless the hub reports otherwise.'}})
            if len(json.dumps(results, allow_nan=False).encode()) > 1024 * 1024:
                raise HTTPException(503, 'Settings response is too large.')
            return {'results': results}
