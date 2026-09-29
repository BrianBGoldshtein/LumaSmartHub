from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

import pytest

from luma.fan_runtime import FanRuntime
from luma.scene_devices import SceneDevices
from luma.ir_protocol import send_result
from test_room import runtime, connect, NOW
from test_fans import configure, observed


def devices(service, room, *, now=NOW + timedelta(hours=2), sent=None):
    async def transport(payload):
        if sent is not None: sent.append(payload)
        return send_result('sent_unconfirmed')
    utcnow = now if callable(now) else lambda: now
    fans = FanRuntime(service, transport=transport, utcnow=utcnow)
    room.utcnow = utcnow
    return SceneDevices(service, room, fans, utcnow=utcnow)


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
async def test_real_fan_dispatch_requires_both_route_reviews_and_absolute_proofs(tmp_path):
    service, rt, _, ticks = runtime(tmp_path)
    configure(service.fans, serial=False)
    observed(service.fans); observed(service.fans); observed(service.fans, 'fan_2')
    sent = []
    bound = devices(service, rt, sent=sent)
    assert all(not row['actions'] for row in bound.catalog())
    for fan, row in service.fans.slots.items():
        output = row['route']
        bound.fans.reviewed.add((fan, output['device']['id'], output['emitter']))
    choice = bound.catalog()[0]['actions'][0]; choice.pop('label')
    before = deepcopy(service.fans.overrides)
    assert await bound.dispatch(choice, can_send=lambda: True) == 'unconfirmed'
    assert len(sent) == 1 and sent[0]['action'] == 'send'
    assert service.fans.receipts['fan_1']['kind'] == 'scene' and service.fans.overrides == before
    # Relinking either physical route invalidates the editor's prior capability.
    row = service.fans.slots['fan_2']
    service.fans.select('fan_2', row['name'], {**row['route'], 'emitter': 3},
                        revision=service.fans.revision, generation=service.fans.generation)
    assert await bound.dispatch(choice, can_send=lambda: True) == 'unavailable'
    assert len(sent) == 1
    await bound.fans.close()


@pytest.mark.asyncio
async def test_denied_scene_does_not_discover_or_send_devices(tmp_path):
    service, rt, _, _ = runtime(tmp_path)
    bound = devices(service, rt)
    assert await bound.dispatch({'device': 'purifier'}, can_send=lambda: False) == 'not_sent'
    assert rt.adapter is None
