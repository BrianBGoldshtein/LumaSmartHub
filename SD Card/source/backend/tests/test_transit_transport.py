import json
import logging
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import httpx
import pytest

from luma.storage import Storage
from luma.transit_transport import TransitBudget,TransitTransport,TransitUnavailable,TransitQuota


TOKEN='synthetic_511_token_for_tests_only'


def test_budget_survives_restart_and_expires_only_after_rolling_hour(tmp_path):
    store=Storage(tmp_path/'test.db');clock=[10000.0]
    for _ in range(55):TransitBudget(store,lambda:clock[0]).reserve()
    with pytest.raises(TransitQuota):TransitBudget(Storage(store.path),lambda:clock[0]).reserve()
    clock[0]+=3599
    with pytest.raises(TransitQuota):TransitBudget(store,lambda:clock[0]).reserve()
    clock[0]+=1
    TransitBudget(store,lambda:clock[0]).reserve()
    assert store.get_cache('transit','budget')==[13600.0]


def test_concurrent_clients_cannot_overdraw_budget(tmp_path):
    store=Storage(tmp_path/'test.db')
    def reserve(_):
        try:TransitBudget(store,lambda:10000).reserve();return True
        except TransitQuota:return False
    with ThreadPoolExecutor(max_workers=8) as pool:assert sum(pool.map(reserve,range(90)))==55


@pytest.mark.parametrize('payload',[{},'bad',[float('nan')],[True],[1]*56])
def test_corrupt_history_fails_closed_without_overwriting(tmp_path,payload):
    store=Storage(tmp_path/'test.db');store.set_cache('transit','budget',payload)
    before=json.dumps(store.get_cache('transit','budget'))
    with pytest.raises(TransitQuota):TransitBudget(store,lambda:10000).reserve()
    assert json.dumps(store.get_cache('transit','budget'))==before


def test_clock_rollback_does_not_replenish_allowance(tmp_path):
    store=Storage(tmp_path/'test.db');TransitBudget(store,lambda:10000).reserve()
    with pytest.raises(TransitQuota):TransitBudget(store,lambda:9999).reserve()


def test_transport_uses_https_no_redirects_token_redaction_and_bom_json(tmp_path,caplog):
    store=Storage(tmp_path/'test.db');requests=[]
    def handler(request):
        requests.append(request)
        return httpx.Response(200,content=b'\xef\xbb\xbf{"ok":true}')
    caplog.set_level(logging.INFO,logger='httpx')
    transport=TransitTransport(TransitBudget(store),lambda:TOKEN,transport=httpx.MockTransport(handler))
    try:assert transport.request('operators')=={'ok':True}
    finally:transport.close()
    assert str(requests[0].url).startswith('https://api.511.org/transit/operators?')
    assert requests[0].url.params['api_key']==TOKEN
    assert TOKEN not in caplog.text and '[redacted]' in caplog.text
    assert len(store.get_cache('transit','budget'))==1


@pytest.mark.parametrize('status',[301,401,403,429,500])
def test_every_failed_attempt_counts_no_retry_or_raw_secret_errors(tmp_path,status):
    store=Storage(tmp_path/'test.db');calls=[]
    def handler(request):calls.append(request);return httpx.Response(status,headers={'location':'https://evil.invalid'},text=TOKEN)
    transport=TransitTransport(TransitBudget(store),lambda:TOKEN,transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(TransitUnavailable) as error:transport.request('StopMonitoring',agency='example')
        assert TOKEN not in str(error.value)
    finally:transport.close()
    assert len(calls)==1 and len(store.get_cache('transit','budget'))==1


def test_oversize_invalid_json_and_disk_failure_are_bounded(tmp_path):
    store=Storage(tmp_path/'test.db');calls=[]
    def handler(request):calls.append(request);return httpx.Response(200,text='x'*100)
    transport=TransitTransport(TransitBudget(store),lambda:TOKEN,transport=httpx.MockTransport(handler));transport.MAX_BYTES=32
    try:
        with pytest.raises(TransitUnavailable,match='limit'):transport.request('operators')
        transport.MAX_BYTES=200
        with pytest.raises(TransitUnavailable,match='read'):transport.request('operators')
        with patch.object(store,'transaction',side_effect=OSError('disk full')):
            with pytest.raises(OSError):transport.request('operators')
        assert len(calls)==2
    finally:transport.close()


def test_missing_key_and_unapproved_endpoint_do_not_spend_quota(tmp_path):
    store=Storage(tmp_path/'test.db')
    transport=TransitTransport(TransitBudget(store),lambda:None,transport=httpx.MockTransport(lambda req:pytest.fail('No request allowed')))
    try:
        with pytest.raises(TransitUnavailable):transport.request('operators')
        with pytest.raises(TransitUnavailable):transport.request('../anything')
        assert store.get_cache('transit','budget') is None
    finally:transport.close()
