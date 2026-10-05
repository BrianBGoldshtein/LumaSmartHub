import asyncio
from dataclasses import asdict
from pathlib import Path
from unittest.mock import Mock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import httpx
import pytest

from luma.api import create_app
from luma import keyword_asset
from luma.keyword_runtime import KeywordAssetRuntime, install_keyword_api


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    result = KeywordAssetRuntime(tmp_path)
    monkeypatch.setattr(result, 'supported', lambda: True)
    monkeypatch.setattr(keyword_asset, 'recover_interrupted_install', Mock())
    monkeypatch.setattr(keyword_asset, 'fetch_and_install', Mock())
    return result


def test_temporary_preview_cannot_fetch_even_with_native_environment(tmp_path, monkeypatch):
    monkeypatch.setenv('LUMA_DATA_DIR', '/var/lib/luma')
    monkeypatch.setattr(keyword_asset, '_runtime_supported', lambda: True)
    runtime = KeywordAssetRuntime(tmp_path)
    assert not runtime.supported()
    assert not runtime.status()['runtime_supported']
    with pytest.raises(HTTPException) as error:
        runtime.start()
    assert error.value.status_code == 409
    assert not runtime.root.exists()


@pytest.mark.asyncio
async def test_prepare_recovers_then_installs_once_and_never_selects_a_detector(runtime):
    calls = []
    keyword_asset.recover_interrupted_install.side_effect = lambda root: calls.append(('recover', root))
    keyword_asset.fetch_and_install.side_effect = lambda **args: calls.append(('fetch', args))
    response = runtime.start()
    assert response['job_active'] and response['phase'] == 'queued'
    with pytest.raises(HTTPException, match='409'):
        runtime.start()
    await runtime.task
    assert calls == [('recover', runtime.root), ('fetch', {'root': runtime.root, 'replace_existing': False})]
    assert not runtime.busy
    assert not runtime.root.exists()  # mock install; no settings/activation write


@pytest.mark.asyncio
@pytest.mark.parametrize('error,expected', [
    (keyword_asset.KeywordAssetError('keyword_download_failed'), 'keyword_download_failed'),
    (keyword_asset.KeywordAssetError('private /path account@example.com'), 'keyword_install_failed'),
    (RuntimeError('sensitive upstream body'), 'keyword_install_failed'),
])
async def test_errors_are_fixed_and_failed_job_can_retry(runtime, error, expected):
    keyword_asset.fetch_and_install.side_effect = error
    runtime.start()
    await runtime.task
    assert runtime.status()['error'] == expected
    assert runtime.status()['phase'] == 'failed'
    keyword_asset.fetch_and_install.side_effect = None
    runtime.start()
    await runtime.task
    assert runtime.status()['error'] is None


@pytest.mark.asyncio
async def test_recovery_failure_never_downloads_over_uncertain_state(runtime):
    keyword_asset.recover_interrupted_install.side_effect = keyword_asset.KeywordAssetError('keyword_recovery_required')
    runtime.start()
    await runtime.task
    keyword_asset.fetch_and_install.assert_not_called()
    assert runtime.status()['error'] == 'keyword_recovery_required'


@pytest.mark.asyncio
async def test_repair_requires_previous_ready_model(runtime, monkeypatch):
    with pytest.raises(HTTPException):
        runtime.start(repair=True)
    monkeypatch.setattr(keyword_asset, 'ready', lambda root, *args: True)
    runtime.start(repair=True)
    await runtime.task
    keyword_asset.fetch_and_install.assert_called_once_with(root=runtime.root, replace_existing=True)


@pytest.mark.asyncio
async def test_busy_voice_operation_blocks_job_before_native_work(runtime):
    runtime.busy_check = lambda: True
    with pytest.raises(HTTPException):
        runtime.start()
    assert runtime.task is None
    keyword_asset.fetch_and_install.assert_not_called()


@pytest.mark.asyncio
async def test_shutdown_joins_owned_thread_instead_of_cancelling_it(runtime, monkeypatch):
    entered, released = asyncio.Event(), asyncio.Event()
    async def controlled_thread(function, *args, **kwargs):
        if function is keyword_asset.fetch_and_install:
            entered.set()
            await released.wait()
        return function(*args, **kwargs)
    monkeypatch.setattr(asyncio, 'to_thread', controlled_thread)
    runtime.start()
    await entered.wait()
    closing = asyncio.create_task(runtime.close())
    await asyncio.sleep(0)
    assert not closing.done()
    assert runtime.closing
    with pytest.raises(HTTPException):
        runtime.start()
    released.set()
    await closing
    assert runtime.task.done() and not runtime.task.cancelled()


@pytest.mark.asyncio
async def test_auto_start_recovers_existing_ready_model_without_redownload(runtime, monkeypatch):
    monkeypatch.setattr(keyword_asset, 'ready', lambda root, *args: True)
    driver = asyncio.create_task(runtime.run(initial_delay=0, retry_seconds=1000))
    for _ in range(100):
        if keyword_asset.recover_interrupted_install.called:
            break
        await asyncio.sleep(.001)
    assert keyword_asset.recover_interrupted_install.call_count == 1
    await runtime.close()
    driver.cancel()
    with pytest.raises(asyncio.CancelledError):
        await driver
    keyword_asset.fetch_and_install.assert_not_called()


@pytest.mark.asyncio
async def test_auto_start_of_preview_does_nothing(tmp_path, monkeypatch):
    fetch = Mock()
    monkeypatch.setattr(keyword_asset, 'fetch_and_install', fetch)
    runtime = KeywordAssetRuntime(tmp_path)
    await runtime.run(initial_delay=0)
    fetch.assert_not_called()
    assert not runtime.root.exists()


@pytest.mark.asyncio
async def test_api_requires_explicit_typed_consent_and_returns_nonblocking_job(runtime):
    app = FastAPI()
    install_keyword_api(app, runtime, lambda: None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
        for body, code in [({}, 422), ({'confirmed':'true'}, 422), ({'confirmed':True,'extra':1}, 422), ({'confirmed':False}, 400)]:
            result = await client.post('/api/v1/voice/keyword-asset/prepare', json=body)
            assert result.status_code == code
        assert runtime.task is None
        result = await client.post('/api/v1/voice/keyword-asset/prepare', json={'confirmed':True})
        assert result.status_code == 200
        assert result.json()['job_active']
        await runtime.task


def test_real_api_status_is_local_only_and_does_not_modify_saved_settings(tmp_path):
    app = create_app(data_dir=tmp_path)
    initial = asdict(app.state.luma.settings)
    client = TestClient(app)
    response = client.get('/api/v1/voice/keyword-asset')
    assert response.status_code == 200
    assert not response.json()['asset_available']
    assert client.post('/api/v1/voice/keyword-asset/prepare', json={'confirmed':True}).status_code == 409
    assert asdict(app.state.luma.settings) == initial
    assert not (tmp_path/'keyword-assets').exists()
    remote = TestClient(app, client=('192.0.2.10', 1000))
    for path in ('', '/prepare', '/repair'):
        response = (remote.post('/api/v1/voice/keyword-asset'+path, json={'confirmed':True})
                    if path else remote.get('/api/v1/voice/keyword-asset'))
        assert response.status_code == 403
    assert client.get('/api/v1/voice/keyword-asset', headers={'Origin':'https://evil.example'}).status_code == 403


def test_real_api_voice_checks_are_interlocked_during_model_install(tmp_path):
    app = create_app(data_dir=tmp_path)
    runtime = app.state.keyword_asset_runtime
    runtime.task = type('Pending', (), {'done':lambda self:False})()
    client = TestClient(app)
    for path, body in [
        ('calibration/start', {}), ('call-trial/start', {}), ('speaker-trial/start', {'confirmed':True}),
        ('speaker-trial/model/install', {'confirmed':True}), ('hardware/gain', {'gain':40}),
        ('asset/retry', {}), ('asset/repair', {}), ('asset/preview', {'variant':'piper'}), ('asset/tone', {}),
    ]:
        result = client.post('/api/v1/voice/'+path, json=body)
        assert result.status_code == 409, (path, result.text)
        assert result.json()['detail'] == 'Wait for the signed wake model to finish preparing.'
