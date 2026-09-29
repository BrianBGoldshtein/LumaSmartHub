"""Pinned Core300S adapter, with bounded transport and no automatic command retry.

This component has no background task or disk access. The room runtime owns
selection, private credential storage, polling/backoff and authorization.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
from importlib.metadata import version
import json
import logging
import re
from zoneinfo import ZoneInfo

import httpx
from pyvesync import VeSync
from pyvesync.devices.vesyncpurifier import VeSyncAirBypass
from pyvesync.utils.errors import ErrorTypes, VeSyncLoginError, VeSyncTokenError
from pyvesync.utils.helpers import Helpers

LIBRARY_VERSION = '3.4.2'
CORE300_TYPES = frozenset({'Core300S', 'LAP-C301S-WJP', 'LAP-C302S-WUSB',
                           'LAP-C301S-WAAA', 'LAP-C302S-WGC'})
HOSTS = {'US': 'https://smartapi.vesync.com', 'EU': 'https://smartapi.vesync.eu'}
AUTH = '/globalPlatform/api/accountAuth/v1/authByPWDOrOTM'
LOGIN = '/user/api/accountManage/v1/loginByAuthorizeCode4Vesync'
DEVICES = '/cloud/v1/deviceManaged/devices'
BYPASS = '/cloud/v2/deviceManaged/bypassV2'
METHODS = frozenset({'getPurifierStatus', 'setSwitch', 'setLevel', 'setPurifierMode', 'setDisplay'})
MAX_RESPONSE = 2 * 1024 * 1024
OPERATION_TIMEOUT = 20


class PurifierUnavailable(Exception):
    """Safe, fixed UI error. Never wrap provider text in this exception."""


class PurifierReconnect(PurifierUnavailable):
    pass


class PurifierRateLimit(PurifierUnavailable):
    pass


class PurifierBusy(PurifierUnavailable):
    pass


class _DropProviderLogs(logging.Filter):
    def filter(self, record):
        return False


def _private_logging():
    # Third-party error logs can contain device names and provider messages even
    # with its JSON redactor enabled. Luma reports only fixed, bounded statuses.
    logging.getLogger('pyvesync').setLevel(logging.CRITICAL + 1)
    for name in tuple(logging.Logger.manager.loggerDict):
        if name == 'pyvesync' or name.startswith('pyvesync.'):
            logger = logging.getLogger(name)
            if not any(isinstance(item, _DropProviderLogs) for item in logger.filters):
                logger.addFilter(_DropProviderLogs())


def credentials(value):
    """Only these session fields can reach the private secrets store; no password."""
    keys = {'token', 'account_id', 'country_code', 'current_region'}
    if not isinstance(value, dict) or set(value) != keys:
        raise PurifierReconnect('Reconnect VeSync on this hub.')
    if any(not isinstance(value[k], str) or not value[k] or len(value[k]) > 4096
           or re.search(r'[\x00-\x1f\x7f]', value[k]) for k in keys):
        raise PurifierReconnect('Reconnect VeSync on this hub.')
    if not re.fullmatch('[A-Z]{2}', value['country_code']) or value['current_region'] not in HOSTS:
        raise PurifierReconnect('Reconnect VeSync on this hub.')
    return dict(value)


def _bounded_number(value, lower, upper):
    return value if type(value) is int and lower <= value <= upper else None


def _reported(raw):
    if not isinstance(raw, dict) or type(raw.get('enabled')) is not bool:
        raise PurifierUnavailable('Purifier status is unavailable.')
    if type(raw.get('device_error_code')) is not int or raw['device_error_code'] != 0:
        raise PurifierUnavailable('The purifier reported a device error.')
    if raw.get('mode') not in ('manual', 'auto', 'sleep') or _bounded_number(raw.get('level'), 0, 3) is None:
        raise PurifierUnavailable('Purifier status is unavailable.')
    if _bounded_number(raw.get('filter_life'), 0, 100) is None:
        raise PurifierUnavailable('Purifier status is unavailable.')
    config = raw.get('configuration')
    display_setting = config.get('display') if isinstance(config, dict) else None
    return {'power': raw['enabled'], 'mode': raw['mode'], 'speed': _bounded_number(raw['level'], 1, 3),
            'display': raw.get('display') if type(raw.get('display')) is bool else None,
            'display_setting': display_setting if type(display_setting) is bool else None,
            'pm25': _bounded_number(raw.get('air_quality_value'), 0, 10000),
            'air_quality_level': _bounded_number(raw.get('air_quality'), 1, 4),
            'filter_percent': raw['filter_life']}


class _BoundedVeSync(VeSync):
    """Keep library models/methods; replace its unbounded, retrying HTTP boundary."""
    def __init__(self, client, *, timezone, username='', password='', country='US'):
        super().__init__(username, password, country_code=country, time_zone=timezone, redact=True)
        self.client = client
        self.auth_calls = 0
        self.reported = None

    async def async_call_api(self, api, method, json_object=None, headers=None, device=None):
        if api not in (AUTH, LOGIN, DEVICES, BYPASS) or method.lower() != 'post':
            raise PurifierUnavailable('Unsupported purifier operation.')
        body = json_object if isinstance(json_object, dict) else json_object.to_dict()
        if not isinstance(body, dict) or len(json.dumps(body)) > 65536:
            raise PurifierUnavailable('Unsupported purifier request.')
        if api in (AUTH, LOGIN):
            self.auth_calls += 1
            if self.auth_calls > 4:
                raise PurifierReconnect('VeSync sign-in could not finish. Check the account region.')
        if api == BYPASS and body.get('payload', {}).get('method') not in METHODS:
            raise PurifierUnavailable('Unsupported purifier operation.')
        if self.current_region not in HOSTS:
            raise PurifierReconnect('Reconnect VeSync on this hub.')
        async with self.client.stream('POST', HOSTS[self.current_region] + api,
                                      json=body, headers=headers, follow_redirects=False) as response:
            if response.status_code in (401, 403):
                raise PurifierReconnect('Reconnect VeSync on this hub.')
            if response.status_code == 429:
                raise PurifierRateLimit('VeSync is limiting requests. Wait before trying again.')
            if response.status_code != 200:
                raise PurifierUnavailable('VeSync is unavailable. Nothing has been queued.')
            content = bytearray()
            async for chunk in response.aiter_bytes():
                if len(content) + len(chunk) > MAX_RESPONSE:
                    raise PurifierUnavailable('VeSync returned an unsupported response.')
                content.extend(chunk)
        try:
            result = json.loads(content)
        except (ValueError, UnicodeError):
            raise PurifierUnavailable('VeSync returned an unsupported response.') from None
        if not isinstance(result, dict):
            raise PurifierUnavailable('VeSync returned an unsupported response.')
        info = Helpers.parse_error_code(result)
        if info.error_type in (ErrorTypes.TOKEN_ERROR, ErrorTypes.AUTHENTICATION):
            # Do not call the library's reauthenticate/replay path, especially
            # after a command whose outcome may be uncertain.
            raise PurifierReconnect('Reconnect VeSync on this hub.')
        if info.error_type == ErrorTypes.RATE_LIMIT:
            raise PurifierRateLimit('VeSync is limiting requests. Wait before trying again.')
        if api == LOGIN and info.error_type == ErrorTypes.CROSS_REGION:
            return result, 200  # Library handles region exchange, bounded above.
        if type(result.get('code')) is not int or result['code'] != 0 or info.device_online is False:
            raise PurifierUnavailable('The purifier is unavailable. Nothing has been queued.')
        if api == DEVICES:
            page = result.get('result')
            if not isinstance(page, dict) or not isinstance(page.get('list'), list) or len(page['list']) > 100:
                raise PurifierUnavailable('VeSync returned an unsupported device list.')
            # The pinned library loads only one page. Never silently omit later
            # devices from a larger account and present discovery as complete.
            if type(page.get('total')) is not int or page['total'] != len(page['list']) or page.get('pageNo') != 1:
                raise PurifierUnavailable('This VeSync account exceeds the supported discovery size.')
        if api == BYPASS:
            outer = result.get('result')
            if not isinstance(outer, dict) or type(outer.get('code')) is not int or outer['code'] != 0:
                raise PurifierUnavailable('The purifier did not confirm the request.')
            if body['payload']['method'] == 'getPurifierStatus':
                self.reported = (body.get('cid'), _reported(outer.get('result')))
        return result, 200


class PurifierAdapter:
    """One serialized owner-selected purifier session. No automatic background I/O."""
    def __init__(self, saved_credentials=None, *, timezone='America/Los_Angeles', transport=None):
        if version('pyvesync') != LIBRARY_VERSION:
            raise PurifierUnavailable('The installed purifier library needs a compatible Luma update.')
        ZoneInfo(timezone)
        _private_logging()
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(10, connect=5), trust_env=False,
                                       follow_redirects=False, transport=transport)
        self.manager = _BoundedVeSync(self.client, timezone=timezone)
        self.timezone = timezone
        self.lock = asyncio.Lock()
        self.devices = {}
        self.capabilities = {}
        if saved_credentials is not None:
            saved = credentials(saved_credentials)
            self.manager.set_credentials(saved['token'], saved['account_id'], saved['country_code'], saved['current_region'])
            self.manager.enabled = True

    @asynccontextmanager
    async def _operation(self):
        if self.lock.locked():
            raise PurifierBusy('Another purifier operation is in progress. Nothing has been queued.')
        async with self.lock:
            try:
                async with asyncio.timeout(OPERATION_TIMEOUT):
                    yield
            except PurifierUnavailable:
                raise
            except (VeSyncLoginError, VeSyncTokenError) as exc:
                if isinstance(exc.__cause__, PurifierUnavailable):
                    raise exc.__cause__ from None
                if isinstance(exc.__cause__, httpx.HTTPError):
                    raise PurifierUnavailable('VeSync is unavailable. Nothing has been queued.') from None
                raise PurifierReconnect('Reconnect VeSync on this hub.') from None
            except Exception:
                raise PurifierUnavailable('VeSync is unavailable. Nothing has been queued.') from None

    async def login(self, username, password, country='US'):
        if not isinstance(username, str) or not 1 <= len(username) <= 254 or not isinstance(password, str) or not 1 <= len(password) <= 512:
            raise PurifierReconnect('Enter your VeSync credentials on this hub.')
        if not isinstance(country, str) or not re.fullmatch('[A-Z]{2}', country):
            raise PurifierReconnect('Choose the account country.')
        async with self._operation():
            candidate = _BoundedVeSync(self.client, timezone=self.timezone, username=username, password=password, country=country)
            try:
                if not await candidate.login():
                    raise PurifierReconnect('Reconnect VeSync on this hub.')
                saved = credentials(candidate.output_credentials_dict())
            finally:
                # Pinned internal fields: no password remains in a long-lived
                # manager and the runtime never persists username/password.
                candidate.auth._username = ''
                candidate.auth._password = ''
            self.manager = candidate
            self.devices.clear()
            self.capabilities.clear()
            return saved  # Internal only: caller stores secret, never an API body.

    async def discover(self):
        async with self._operation():
            if not self.manager.enabled:
                raise PurifierReconnect('Connect VeSync on this hub first.')
            if not await self.manager.get_devices():
                raise PurifierUnavailable('Could not load VeSync devices.')
            devices = {}
            for device in self.manager.devices.air_purifiers:
                if isinstance(device, VeSyncAirBypass) and device.device_type in CORE300_TYPES:
                    key = 'purifier-' + sha256(device.cid.encode()).hexdigest()[:24]
                    devices[key] = device
            if len(devices) > 25:
                raise PurifierUnavailable('Too many supported purifiers in this account.')
            self.devices = devices
            self.capabilities = {key: {'power': True, 'speeds': sorted(set(device.fan_levels) & {1, 2, 3}),
                                      'modes': [mode for mode in ('manual', 'sleep', 'auto') if mode in device.modes],
                                      'display': False} for key, device in devices.items()}
            return [{'id': key, 'name': re.sub(r'[\x00-\x1f\x7f]', '', device.device_name)[:100] or 'Core 300S',
                     'model': device.device_type, 'capabilities': deepcopy(self.capabilities[key])}
                    for key, device in sorted(devices.items())]

    def _device(self, key):
        if not isinstance(key, str) or key not in self.devices:
            raise PurifierUnavailable('Select a discovered Core 300S purifier first.')
        return self.devices[key]

    async def _read(self, key):
        device = self._device(key)
        self.manager.reported = None
        await device.get_details()
        reported = self.manager.reported
        if reported is None or reported[0] != device.cid:
            raise PurifierUnavailable('Purifier status is unavailable.')
        state = deepcopy(reported[1])
        self.capabilities[key]['display'] = state['display'] is not None or state['display_setting'] is not None
        return {'id': key, 'reported_at': datetime.now(UTC).isoformat(), 'state': state,
                'capabilities': deepcopy(self.capabilities[key])}

    async def read(self, key):
        async with self._operation():
            return await self._read(key)

    async def command(self, key, action, value, *, can_send=lambda: True):
        attempt = {'sent': False}
        try:
            return await self._command(key, action, value, attempt, can_send)
        except PurifierUnavailable:
            if attempt['sent']:
                return {'status': 'unconfirmed', 'accepted': None, 'reported': None,
                        'message': 'The command outcome is unknown. It will not be retried.'}
            raise

    async def _command(self, key, action, value, attempt, can_send):
        device = self._device(key)
        caps = self.capabilities[key]
        valid = ((action in ('power', 'display') and type(value) is bool)
                 or (action == 'speed' and type(value) is int and value in caps['speeds'])
                 or (action == 'mode' and type(value) is str and value in caps['modes']))
        if not valid:
            raise PurifierUnavailable('Choose a supported purifier action.')
        async with self._operation():
            before = await self._read(key)  # Offline/unknown devices never receive a queued command.
            if action == 'display' and not self.capabilities[key]['display']:
                raise PurifierUnavailable('This purifier has not reported display control.')
            if not can_send():
                raise PurifierUnavailable('Device access changed. Nothing was sent.')
            try:
                attempt['sent'] = True
                if action == 'power':
                    accepted = await (device.turn_on() if value else device.turn_off())
                elif action == 'speed':
                    accepted = await device.set_fan_speed(value)
                elif action == 'mode':
                    accepted = await device.set_mode(value)
                else:
                    accepted = await device.toggle_display(value)
            except asyncio.CancelledError:
                raise
            except Exception:
                return {'status': 'unconfirmed', 'accepted': None, 'reported': before,
                        'message': 'The command outcome is unknown. It will not be retried.'}
            if accepted is not True:
                return {'status': 'rejected', 'accepted': False, 'reported': before,
                        'message': 'The purifier did not accept the command.'}
            try:
                after = await self._read(key)
            except asyncio.CancelledError:
                raise
            except Exception:
                return {'status': 'unconfirmed', 'accepted': True, 'reported': before,
                        'message': 'Command accepted; a fresh device state is unavailable.'}
            observed = after['state']['display_setting'] if action == 'display' else after['state'][action]
            confirmed = observed == value if observed is not None else False
            if action in ('speed', 'mode'):
                confirmed = confirmed and after['state']['power'] is True
            if action == 'speed':
                confirmed = confirmed and after['state']['mode'] == 'manual'
            return {'status': 'confirmed' if confirmed else 'unconfirmed', 'accepted': True,
                    'reported': after, 'message': 'Device state confirmed.' if confirmed else
                    'Command accepted; the reported state has not matched yet.'}

    async def close(self):
        # Runtime must cancel/await its worker before closing the adapter.
        async with self.lock:
            await self.client.aclose()
