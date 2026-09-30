from datetime import timedelta

import pytest

from luma.scene_devices import SceneDevices
from test_room import runtime, connect, NOW


def devices(service, room, *, now=NOW + timedelta(hours=2)):
    utcnow = now if callable(now) else lambda: now
    room.utcnow = utcnow
    return SceneDevices(service, room, utcnow=utcnow)


@pytest.mark.asyncio
async def test_real_purifier_scene_uses_claim_preflight_and_readback_without_owner_bypass_on_manual(tmp_path):
    service, rt, provider, ticks = runtime(tmp_path)
    try:
        await connect(rt, ticks)
        bound = devices(service, rt, now=rt.utcnow)
        choice = next(row for row in bound.catalog()[0]['actions'] if row['action'] == 'power' and row['value'] is False)
        choice.pop('label')
        service.update_settings({'onboarding_completed': True})
        assert not rt.owner_allowed()
        assert await bound.dispatch(choice, can_send=lambda: True) == 'confirmed'
        assert provider.command_count == 1 and service.room.override_until is None
        assert service.room.receipt['status'] == 'confirmed'
        with pytest.raises(Exception): await rt.command('power', True, service.room.revision)
    finally: await rt.close()


@pytest.mark.asyncio
async def test_purifier_scene_manual_override_or_stale_binding_sends_nothing(tmp_path):
    service, rt, provider, ticks = runtime(tmp_path)
    try:
        await connect(rt, ticks)
        now = rt.utcnow()
        bound = devices(service, rt, now=now)
        choice = next(row for row in bound.catalog()[0]['actions'] if row['action'] == 'power')
        choice.pop('label')
        service.room.claim('power', False, revision=service.room.revision, generation=service.room.generation, now=now)
        assert await bound.dispatch(choice, can_send=lambda: True) == 'skipped_override'
        assert provider.command_count == 0
        service.room.override_until = None  # Synthetic time advancement for binding case.
        service.room.select(service.room.selected, revision=service.room.revision, generation=service.room.generation)
        assert await bound.dispatch(choice, can_send=lambda: True) == 'unavailable'
        with pytest.raises(ValueError): bound.bind([choice])
    finally: await rt.close()


@pytest.mark.asyncio
async def test_purifier_scene_revoked_in_real_preflight_never_sends(tmp_path):
    import httpx
    from luma.purifier_adapter import PurifierAdapter
    from test_purifier_adapter import Provider, BYPASS
    provider, permission = Provider(), [True]
    service, rt, _, ticks = runtime(tmp_path)
    revoke = [False]
    def handler(request):
        result = provider(request)
        if revoke[0] and request.url.path == BYPASS: permission[0] = False
        return result
    rt.factory = lambda saved=None, **kw: PurifierAdapter(saved, transport=httpx.MockTransport(handler), **kw)
    try:
        await connect(rt, ticks)
        bound = devices(service, rt, now=rt.utcnow())
        choice = next(row for row in bound.catalog()[0]['actions'] if row['action'] == 'power')
        choice.pop('label'); revoke[0] = True
        assert await bound.dispatch(choice, can_send=lambda: permission[0]) == 'unconfirmed'
        assert provider.command_count == 0 and service.room.receipt['status'] == 'not_sent'
    finally: await rt.close()


@pytest.mark.asyncio
async def test_denied_scene_does_not_discover_or_send_devices(tmp_path):
    service, rt, _, _ = runtime(tmp_path)
    bound = devices(service, rt)
    assert await bound.dispatch({'device': 'purifier'}, can_send=lambda: False) == 'not_sent'
    assert rt.adapter is None
