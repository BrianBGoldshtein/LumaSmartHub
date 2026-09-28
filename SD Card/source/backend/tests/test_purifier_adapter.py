"""Real pinned library exercised through synthetic HTTP; no account or hardware."""
import asyncio
from copy import deepcopy
import json
import logging

import httpx
import pytest
import pytest_asyncio

from luma.purifier_adapter import (
    AUTH, LOGIN, DEVICES, BYPASS, MAX_RESPONSE, PurifierAdapter, PurifierBusy,
    PurifierReconnect, PurifierRateLimit, PurifierUnavailable, credentials,
)

SECRET = {'token': 'QA_TOKEN_SENTINEL', 'account_id': 'QA_ACCOUNT_SENTINEL',
          'country_code': 'US', 'current_region': 'US'}


def device(cid='QA_CID_SENTINEL', model='Core300S'):
    return {'deviceRegion': 'US', 'isOwner': True, 'deviceName': 'QA purifier',
            'cid': cid, 'connectionType': 'wifi', 'deviceType': model, 'type': 'wifi',
            'configModule': 'WiFi', 'deviceStatus': 'on', 'connectionStatus': 'online'}


class Provider:
    def __init__(self):
        self.calls = []
        self.devices = [device(), device('OTHER', 'Core400S')]
        self.raw = {'enabled': True, 'filter_life': 72, 'mode': 'manual', 'level': 2,
                    'device_error_code': 0, 'display': True, 'air_quality': 1,
                    'air_quality_value': 7, 'configuration': {'display': True}}
        self.fail = None
        self.adopt = True
        self.fail_after_command = False
        self.command_count = 0

    def __call__(self, request):
        body = json.loads(request.content)
        path = request.url.path
        self.calls.append((path, body))
        assert request.url.scheme == 'https' and request.url.host in ('smartapi.vesync.com', 'smartapi.vesync.eu')
        if self.fail is not None:
            return self.fail(request)
        if path == AUTH:
            return httpx.Response(200, json={'code': 0, 'msg': None, 'traceId': 'QA_TRACE', 'result': {'accountID': SECRET['account_id'], 'authorizeCode': 'QA_CODE'}})
        if path == LOGIN:
            return httpx.Response(200, json={'code': 0, 'msg': None, 'traceId': 'QA_TRACE', 'result': {'accountID': SECRET['account_id'], 'token': SECRET['token'],
                                  'acceptLanguage': 'en', 'countryCode': 'US', 'currentRegion': 'US'}})
        if path == DEVICES:
            return httpx.Response(200, json={'code': 0, 'msg': None, 'traceId': 'QA_TRACE', 'result': {'total': len(self.devices), 'pageSize': 100,
                                  'pageNo': 1, 'list': deepcopy(self.devices)}})
        assert path == BYPASS
        method = body['payload']['method']
        if method == 'getPurifierStatus':
            if self.fail_after_command and self.command_count:
                raise httpx.ConnectError('QA_TOKEN_SENTINEL secret error', request=request)
            return httpx.Response(200, json={'code': 0, 'msg': None, 'traceId': 'QA_TRACE', 'result': {'code': 0, 'result': deepcopy(self.raw)}})
        self.command_count += 1
        if self.adopt:
            values = body['payload']['data']
            if method == 'setSwitch': self.raw['enabled'] = values['enabled']
            elif method == 'setLevel': self.raw.update(level=values['level'], mode='manual', enabled=True)
            elif method == 'setPurifierMode': self.raw.update(mode=values['mode'], enabled=True)
            elif method == 'setDisplay': self.raw['configuration']['display'] = values['state']
            else: raise AssertionError('Unexpected mutation')
        return httpx.Response(200, json={'code': 0, 'msg': None, 'traceId': 'QA_TRACE', 'result': {'code': 0, 'result': {}}})


@pytest_asyncio.fixture
async def connected():
    provider = Provider()
    adapter = PurifierAdapter(SECRET, transport=httpx.MockTransport(provider))
    try:
        found = await adapter.discover()
        yield adapter, provider, found[0]['id']
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_real_library_discovery_limits_models_and_does_not_poll_every_device(connected):
    adapter, provider, key = connected
    assert len(adapter.devices) == 1 and key.startswith('purifier-')
    assert [path for path, _ in provider.calls] == [DEVICES]
    result = await adapter.read(key)
    assert result['state']['power'] is True and result['state']['pm25'] == 7
    assert result['state']['filter_percent'] == 72
    assert result['capabilities'] == {'power': True, 'speeds': [1, 2, 3], 'modes': ['manual', 'sleep', 'auto'], 'display': True}
    for secret in ('QA_TOKEN_SENTINEL', 'QA_ACCOUNT_SENTINEL', 'QA_CID_SENTINEL'):
        assert secret not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(('action', 'value'), [('power', False), ('power', True), ('speed', 3), ('mode', 'sleep'), ('mode', 'auto'), ('display', False)])
async def test_absolute_commands_require_fresh_readback(connected, action, value):
    adapter, provider, key = connected
    result = await adapter.command(key, action, value)
    assert result['status'] == 'confirmed' and result['accepted'] is True
    assert provider.command_count == 1
    assert [body['payload']['method'] for path, body in provider.calls if path == BYPASS][0] == 'getPurifierStatus'
    assert provider.calls[-1][1]['payload']['method'] == 'getPurifierStatus'


@pytest.mark.asyncio
async def test_library_optimistic_state_is_not_reported_as_device_confirmation(connected):
    adapter, provider, key = connected
    provider.adopt = False
    result = await adapter.command(key, 'power', False)
    assert result['status'] == 'unconfirmed' and result['accepted'] is True
    assert result['reported']['state']['power'] is True
    provider.fail_after_command = True
    # A fresh command accepted by the API but failed readback stays unconfirmed.
    provider.command_count = 0
    result = await adapter.command(key, 'speed', 3)
    assert result['status'] == 'unconfirmed' and result['accepted'] is True
    assert result['reported']['state']['speed'] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(('action', 'value'), [('reset_filter', True), ('toggle', None), ('power', 1), ('speed', True), ('speed', 4), ('mode', 'turbo'), ('display', 'off')])
async def test_invalid_or_unsupported_actions_never_reach_network(connected, action, value):
    adapter, provider, key = connected
    count = len(provider.calls)
    with pytest.raises(PurifierUnavailable): await adapter.command(key, action, value)
    assert len(provider.calls) == count


@pytest.mark.asyncio
async def test_missing_display_field_removes_control_and_missing_metrics_stay_unknown(connected):
    adapter, provider, key = connected
    for field in ('display', 'configuration', 'air_quality_value', 'air_quality'):
        provider.raw.pop(field)
    result = await adapter.read(key)
    assert result['state']['pm25'] is None and result['state']['air_quality_level'] is None
    assert not result['capabilities']['display']
    with pytest.raises(PurifierUnavailable): await adapter.command(key, 'display', False)
    assert not provider.command_count


@pytest.mark.asyncio
@pytest.mark.parametrize('code', [401, 403, 429, 500, 302])
async def test_http_failures_are_safe_and_never_redirect_or_retry(connected, code):
    adapter, provider, key = connected
    provider.fail = lambda _: httpx.Response(code, headers={'location': 'https://evil.invalid/secret'}, text='QA_TOKEN_SENTINEL')
    count = len(provider.calls)
    error = PurifierReconnect if code in (401, 403) else PurifierRateLimit if code == 429 else PurifierUnavailable
    with pytest.raises(error) as caught: await adapter.read(key)
    assert len(provider.calls) == count + 1 and 'QA_TOKEN_SENTINEL' not in str(caught.value)


@pytest.mark.asyncio
async def test_busy_commands_rejected_not_queued(connected):
    adapter, provider, key = connected
    async with adapter.lock:
        with pytest.raises(PurifierBusy): await adapter.command(key, 'power', False)
    assert provider.command_count == 0


@pytest.mark.asyncio
async def test_login_uses_library_protocol_and_retains_only_session_fields(caplog):
    provider = Provider()
    adapter = PurifierAdapter(transport=httpx.MockTransport(provider))
    try:
        with caplog.at_level(logging.DEBUG):
            saved = await adapter.login('QA_EMAIL_SENTINEL', 'QA_PASSWORD_SENTINEL')
        assert saved == SECRET
        assert adapter.manager.auth._password == '' and adapter.manager.auth._username == ''
        assert [path for path, _ in provider.calls] == [AUTH, LOGIN]
        assert provider.calls[0][1]['password'] != 'QA_PASSWORD_SENTINEL'
        assert all(secret not in caplog.text for secret in (*SECRET.values(), 'QA_EMAIL_SENTINEL', 'QA_PASSWORD_SENTINEL'))
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_malformed_device_response_cannot_reuse_previous_state(connected):
    adapter, provider, key = connected
    await adapter.read(key)
    provider.raw.pop('enabled')
    with pytest.raises(PurifierUnavailable): await adapter.read(key)
    assert provider.command_count == 0


@pytest.mark.asyncio
async def test_response_size_is_bounded(connected):
    adapter, provider, key = connected
    provider.fail = lambda _: httpx.Response(200, content=b'x' * (MAX_RESPONSE + 1))
    with pytest.raises(PurifierUnavailable): await adapter.read(key)


@pytest.mark.parametrize('bad', [{}, {**SECRET, 'password': 'never'}, {**SECRET, 'current_region': 'https://evil.invalid'}, {**SECRET, 'token': 'x\nsecret'}])
def test_private_session_schema_excludes_password_and_arbitrary_regions(bad):
    with pytest.raises(PurifierReconnect): credentials(bad)


@pytest.mark.asyncio
async def test_login_failure_clears_password_and_preserves_existing_session(monkeypatch):
    from luma import purifier_adapter as module
    provider = Provider()
    provider.fail = lambda _: httpx.Response(429, text='QA_PASSWORD_SENTINEL')
    adapter = PurifierAdapter(SECRET, transport=httpx.MockTransport(provider))
    original = adapter.manager
    candidates = []
    factory = module._BoundedVeSync
    def record(*args, **kwargs):
        candidate = factory(*args, **kwargs)
        candidates.append(candidate)
        return candidate
    monkeypatch.setattr(module, '_BoundedVeSync', record)
    try:
        with pytest.raises(PurifierRateLimit): await adapter.login('QA_EMAIL', 'QA_PASSWORD_SENTINEL')
        assert candidates[0].auth._password == '' and candidates[0].auth._username == ''
        assert adapter.manager is original
        assert len(provider.calls) == 1
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_command_timeout_after_send_is_unknown_and_not_replayed(monkeypatch):
    from luma import purifier_adapter as module
    provider = Provider()
    entered = asyncio.Event()
    async def delayed(request):
        result = provider(request)
        if provider.command_count:
            entered.set()
            await asyncio.sleep(1)
        return result
    adapter = PurifierAdapter(SECRET, transport=httpx.MockTransport(delayed))
    try:
        key = (await adapter.discover())[0]['id']
        monkeypatch.setattr(module, 'OPERATION_TIMEOUT', 0.04)
        result = await adapter.command(key, 'power', False)
        assert entered.is_set() and provider.command_count == 1
        assert result['status'] == 'unconfirmed' and result['accepted'] is None
        assert 'retry' not in result['message'] or 'not' in result['message']
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_expired_session_never_attempts_password_login_or_command_retry(connected):
    adapter, provider, key = connected
    # Actual library token-error code, not an arbitrary fake classification.
    from pyvesync.utils.errors import ErrorCodes, ErrorTypes
    code = -11001000
    assert ErrorCodes.get_error_info(code).error_type == ErrorTypes.TOKEN_ERROR
    provider.fail = lambda _: httpx.Response(200, json={'code': code, 'msg': 'QA_TOKEN_SENTINEL'})
    before = len(provider.calls)
    with pytest.raises(PurifierReconnect): await adapter.read(key)
    assert len(provider.calls) == before + 1
    assert all(path not in (AUTH, LOGIN) for path, _ in provider.calls)


@pytest.mark.asyncio
async def test_unknown_device_and_arbitrary_endpoint_cannot_issue_commands(connected):
    adapter, provider, key = connected
    count = len(provider.calls)
    with pytest.raises(PurifierUnavailable): await adapter.command('other-device', 'power', True)
    with pytest.raises(PurifierUnavailable): await adapter.manager.async_call_api('/arbitrary', 'POST', {})
    with pytest.raises(PurifierUnavailable): await adapter.manager.async_call_api(BYPASS, 'POST', {'payload': {'method': 'resetFilter'}})
    assert len(provider.calls) == count


@pytest.mark.asyncio
async def test_larger_accounts_are_not_silently_truncated(connected):
    adapter, provider, key = connected
    provider.fail = lambda _: httpx.Response(200, json={'code': 0, 'result': {'list': [device()], 'total': 101, 'pageNo': 1}})
    with pytest.raises(PurifierUnavailable, match='discovery size'): await adapter.discover()
