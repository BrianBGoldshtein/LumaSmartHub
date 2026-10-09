"""Actual local routes and synthetic providers; no appliance/account writes."""
import asyncio
import base64
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from threading import Event
import httpx

import pytest

from luma.admin_authority import COOKIE, LEASE_SECONDS
from luma.models import CalendarEvent
from luma.portable_backup import snapshot
from test_admin_api import protected, unlock
from test_companion_api import client
from test_purifier_adapter import Provider, LOGIN, BYPASS
from luma.purifier_adapter import PurifierAdapter
from test_room import connect
from luma.api import create_app


def revoke(app, clock, connection, kind):
    if kind == 'expiry': clock[0] = LEASE_SECONDS
    elif kind == 'lock': app.state.admin.lock_local(connection.cookies.get(COOKIE))
    else: app.state.security.set_pin('789012')


def denied(response):
    assert response.status_code == 403
    assert response.json()['code'] == 'admin_required'


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['expiry', 'lock', 'pin'])
async def test_backup_export_does_not_dispatch_after_encryption_loses_authority(protected, monkeypatch, kind):
    import luma.backup_api as module
    app, clock = protected
    broker = AsyncMock(return_value={'verified':True})
    monkeypatch.setattr(module, 'backup_request', broker)
    async with client(app) as connection:
        await unlock(connection)
        def encrypt(*args):
            revoke(app, clock, connection, kind)
            return b'synthetic_encrypted_bytes'
        monkeypatch.setattr(module, 'encrypt', encrypt)
        result = await connection.post('/api/v1/backups/export', json={
            'volume_id':'a'*32, 'passphrase':'long synthetic password',
            'confirm_passphrase':'long synthetic password'})
        denied(result)
        broker.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('point', ['restore_lock', 'countdown_lock', 'transit_lock', 'scene_cancel'])
async def test_backup_apply_rechecks_all_waits_before_committing(protected, monkeypatch, point):
    import luma.backup_api as module
    app, clock = protected
    document = snapshot(app.state.luma.storage)
    document['settings']['theme'] = 'hearth'
    monkeypatch.setattr(module, 'backup_request', AsyncMock(return_value={'archive':base64.b64encode(b'x').decode()}))
    monkeypatch.setattr(module, 'decrypt', lambda *args: document)
    apply = Mock(wraps=module.apply_document)
    monkeypatch.setattr(module, 'apply_document', apply)
    async with client(app) as connection:
        await unlock(connection)
        opened = await connection.post('/api/v1/backups/preview', json={
            'volume_id':'a'*32,'backup_id':'b'*32,'passphrase':'long synthetic password'})
        assert opened.status_code == 200
        lock = {'restore_lock':app.state.backup_restore_lock,
                'countdown_lock':app.state.countdown_runtime.refresh_lock,
                'transit_lock':app.state.transit_runtime.lock}.get(point)
        if lock: await lock.acquire()
        else:
            async def cancel(): clock[0] = LEASE_SECONDS
            monkeypatch.setattr(app.state.scene_runtime.executor, 'cancel', cancel)
        pending = asyncio.create_task(connection.post('/api/v1/backups/apply', json={
            'preview_id':opened.json()['preview_id'],'confirmed':True}))
        if lock:
            await asyncio.sleep(.03)
            assert not pending.done()
            clock[0] = LEASE_SECONDS
            lock.release()
        denied(await pending)
        apply.assert_not_called()
        assert app.state.luma.settings.theme.value != 'hearth'


@pytest.mark.asyncio
async def test_expired_backup_preview_never_returns_its_private_summary(protected, monkeypatch):
    import luma.backup_api as module
    app, clock = protected
    document = snapshot(app.state.luma.storage)
    monkeypatch.setattr(module, 'backup_request', AsyncMock(return_value={'archive':base64.b64encode(b'x').decode()}))
    def decrypt(*args):
        clock[0] = LEASE_SECONDS
        return document
    monkeypatch.setattr(module, 'decrypt', decrypt)
    async with client(app) as connection:
        await unlock(connection)
        result = await connection.post('/api/v1/backups/preview', json={
            'volume_id':'a'*32,'backup_id':'b'*32,'passphrase':'long synthetic password'})
        denied(result)
        assert 'preview_id' not in result.text and 'created_at' not in result.text


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['expiry', 'lock', 'pin'])
async def test_transit_favorite_not_saved_after_verification_revoke(protected, monkeypatch, kind):
    app, clock = protected
    async with client(app) as connection:
        await unlock(connection)
        async def verify(**kwargs):
            revoke(app, clock, connection, kind)
            return kwargs
        monkeypatch.setattr(app.state.transit_runtime, 'verified_selection', verify)
        save = Mock()
        monkeypatch.setattr(app.state.luma.transit, 'save', save)
        denied(await connection.post('/api/v1/transit/favorites', json={
            'title':'Lab stop','operator_id':'op','stop_id':'stop'}))
        save.assert_not_called()


@pytest.mark.asyncio
async def test_countdown_google_pin_not_saved_after_provider_lease_expiry(protected, monkeypatch):
    app, clock = protected
    now = datetime.now(UTC)
    monkeypatch.setattr(app.state.google, 'authorized', lambda:True)
    def event(**kwargs):
        clock[0] = LEASE_SECONDS
        return {'state':'ready','event':CalendarEvent('event','calendar','PRIVATE',now,now+timedelta(hours=1))}
    monkeypatch.setattr(app.state.google, 'countdown_event', event)
    save = Mock()
    monkeypatch.setattr(app.state.luma.countdowns, 'pin_google', save)
    async with client(app) as connection:
        await unlock(connection)
        denied(await connection.post('/api/v1/countdowns/google', json={'calendar_id':'calendar','event_id':'event'}))
    save.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('route,body', [
    ('/api/v1/onboarding', {'action':'continue','step':'welcome'}),
    ('/api/v1/network', {'action':'scan'}),
    ('/api/v1/tailscale', {'action':'status'}),
    ('/api/v1/transit/token', {'token':'SYNTHETIC_TOKEN'})])
async def test_streamed_body_must_not_outlive_original_lease(protected, monkeypatch, route, body):
    import json
    import luma.api as module
    app, clock = protected
    network, tail = AsyncMock(), AsyncMock()
    monkeypatch.setattr(module, 'network_request', network)
    monkeypatch.setattr(module, 'tailscale_request', tail)
    previous = app.state.luma.storage.get_cache('onboarding','progress')
    async with client(app) as connection:
        await unlock(connection)
        async def chunks():
            yield b' '
            clock[0] = LEASE_SECONDS
            yield json.dumps(body).encode()
        result = await connection.post(route, content=chunks(), headers={'Content-Type':'application/json'})
        denied(result)
        network.assert_not_awaited()
        tail.assert_not_awaited()
        assert app.state.luma.storage.get_cache('onboarding','progress') == previous
        assert app.state.luma.transit.token() is None


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['expiry', 'lock', 'pin'])
@pytest.mark.parametrize('action', ['login','select','command'])
async def test_real_purifier_preflight_cannot_commit_or_send_after_revoke(protected, kind, action):
    app, clock = protected
    runtime = app.state.room_runtime
    ticks, provider, armed = [1000.0], Provider(), [False]
    runtime.clock = lambda:ticks[0]
    async with client(app) as connection:
        await unlock(connection)
        def handler(request):
            result = provider(request)
            if armed[0] and request.url.path == (LOGIN if action == 'login' else BYPASS):
                revoke(app, clock, connection, kind)
            return result
        runtime.factory = lambda saved=None, **kwargs:PurifierAdapter(saved, transport=httpx.MockTransport(handler), **kwargs)
        try:
            if action != 'login': await connect(runtime, ticks)
            revision, selected, session = runtime.store.revision, runtime.store.selected, runtime.store.session
            armed[0] = True
            if action == 'login':
                result = await connection.post('/api/v1/room/vesync/login', json={
                    'username':'SYNTHETIC_EMAIL','password':'SYNTHETIC_PASSWORD','country':'US','revision':revision})
            elif action == 'select':
                result = await connection.post('/api/v1/room/purifier/select', json={
                    'device_id':selected['id'],'name':'Changed name','revision':revision})
            else:
                result = await connection.post('/api/v1/room/purifier/command', json={
                    'action':'power','value':False,'revision':revision})
            denied(result)
            assert provider.command_count == 0
            assert runtime.store.revision == revision
            assert runtime.store.selected == selected and runtime.store.session == session
            if action == 'command': assert runtime.store.receipt['status'] == 'not_sent'
        finally: await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['expiry', 'lock', 'pin'])
async def test_manual_scene_rechecks_context_at_device_dispatch_and_records_receipt(protected, kind):
    from test_scenes import CONFIG
    app, clock = protected
    runtime = app.state.scene_runtime
    app.state.luma.display_clock_trusted = lambda:True
    runtime.store.edit('morning',CONFIG,revision=runtime.store.revision)
    sent = []
    async with client(app) as connection:
        await unlock(connection)
        async def dispatch(item, *, can_send):
            revoke(app, clock, connection, kind)
            if can_send(): sent.append(item)
            return 'not_sent'
        runtime.executor.dispatch = dispatch
        result = await connection.post('/api/v1/scenes/morning/run',json={'revision':runtime.store.revision})
        denied(result)
        assert sent == []
        receipt = runtime.store.configuration()['runs'][-1]
        assert receipt['steps'][0]['status'] == 'not_sent'
        assert receipt['finished'] is False and receipt['interrupted'] is True


@pytest.mark.asyncio
async def test_request_context_does_not_gate_an_independent_public_timer(protected, monkeypatch):
    import luma.backup_api as module
    from luma.admin_authority import REQUEST_ADMIN
    app, clock = protected
    started, finish = asyncio.Event(), asyncio.Event()
    async def read(request):
        started.set()
        await finish.wait()
        return {'archive':base64.b64encode(b'x').decode()}
    monkeypatch.setattr(module,'backup_request',read)
    monkeypatch.setattr(module,'decrypt',lambda *args:snapshot(app.state.luma.storage))
    async with client(app) as connection:
        await unlock(connection)
        pending = asyncio.create_task(connection.post('/api/v1/backups/preview', json={
            'volume_id':'a'*32,'backup_id':'b'*32,'passphrase':'long synthetic password'}))
        await started.wait()
        clock[0] = LEASE_SECONDS
        timer = await connection.post('/api/v1/commands',json={'name':'start_timer','value':{'seconds':60}})
        assert timer.status_code == 200 and timer.json()['result']['accepted']
        assert REQUEST_ADMIN.get() is None
        finish.set()
        denied(await pending)
        assert REQUEST_ADMIN.get() is None


@pytest.mark.asyncio
async def test_countdown_does_not_query_provider_after_waiting_out_lease(protected, monkeypatch):
    app, clock = protected
    monkeypatch.setattr(app.state.google,'authorized',lambda:True)
    provider = Mock()
    monkeypatch.setattr(app.state.google,'countdown_event',provider)
    lock = app.state.google_sync_lock
    async with client(app) as connection:
        await unlock(connection)
        await lock.acquire()
        pending = asyncio.create_task(connection.post('/api/v1/countdowns/google',json={'calendar_id':'calendar','event_id':'event'}))
        await asyncio.sleep(.03)
        assert not pending.done()
        clock[0] = LEASE_SECONDS
        lock.release()
        denied(await pending)
        provider.assert_not_called()


@pytest.mark.asyncio
async def test_capture_gain_does_not_touch_hardware_after_preflight_revoke(protected, monkeypatch):
    import luma.mic_hardware as module
    app, clock = protected
    def status():
        clock[0] = LEASE_SECONDS
        return {'available':True,'gain':39}
    monkeypatch.setattr(module,'status',status)
    apply = Mock()
    monkeypatch.setattr(module,'save_and_apply',apply)
    async with client(app) as connection:
        await unlock(connection)
        denied(await connection.post('/api/v1/voice/hardware/gain',json={'gain':40}))
        apply.assert_not_called()


@pytest.mark.asyncio
async def test_pin_hash_cannot_commit_after_fresh_confirmation_expires(protected, monkeypatch):
    import luma.security as module
    from luma.admin_authority import FRESH_SECONDS
    app, clock = protected
    previous = app.state.luma.storage.get_secret(module.PIN_SECRET_KEY)
    async with client(app) as connection:
        await unlock(connection)
        original = module.hashlib.scrypt
        def hash(*args,**kwargs):
            value = original(*args,**kwargs)
            clock[0] = FRESH_SECONDS
            return value
        monkeypatch.setattr(module.hashlib,'scrypt',hash)
        result = await connection.post('/api/v1/security/pin',json={'pin':'789012'})
        denied(result)
        assert result.json()['fresh'] is True
        assert app.state.luma.storage.get_secret(module.PIN_SECRET_KEY) == previous


@pytest.mark.asyncio
async def test_google_config_lock_rechecks_in_worker_before_credentials_write(protected, monkeypatch):
    from luma.integrations.google_calendar import CLIENT_CONFIG_KEY
    app, clock = protected
    lock, entered = app.state.google._oauth_lock, Event()
    class Probe:
        def __enter__(self):
            entered.set()
            return lock.__enter__()
        def __exit__(self,*args): return lock.__exit__(*args)
    monkeypatch.setattr(app.state.google,'_oauth_lock',Probe())
    lock.acquire()
    held = True
    try:
        async with client(app) as connection:
            await unlock(connection)
            pending = asyncio.create_task(connection.post('/api/v1/google/config',json={
                'installed':{'client_id':'SYNTHETIC_CLIENT','client_secret':'SYNTHETIC_SECRET'}}))
            assert await asyncio.to_thread(entered.wait,2)
            clock[0] = LEASE_SECONDS
            lock.release()
            held = False
            denied(await pending)
            assert app.state.luma.storage.get_secret(CLIENT_CONFIG_KEY) is None
    finally:
        if held: lock.release()


@pytest.mark.asyncio
async def test_bootstrap_request_cannot_commit_after_other_provisioning_creates_pin(tmp_path):
    import json
    app = create_app(data_dir=tmp_path)
    previous = app.state.luma.storage.get_cache('onboarding','progress')
    async with client(app) as connection:
        async def chunks():
            yield b' '
            app.state.security.set_pin('123456')
            yield json.dumps({'action':'continue','step':'welcome'}).encode()
        denied(await connection.post('/api/v1/onboarding',content=chunks(),headers={'Content-Type':'application/json'}))
        assert app.state.security.pin_is_configured()
        assert app.state.luma.storage.get_cache('onboarding','progress') == previous
