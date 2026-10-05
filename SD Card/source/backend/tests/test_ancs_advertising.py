import asyncio
import os
import shutil
import signal
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from dbus_next import Variant
from dbus_next.service import ServiceInterface
import pytest

from luma.ancs_advertising import ANCSSolicitation, ANCSReconnectAdvertising, MANAGER, PATH, reconnect_adapter
from luma.integrations.ancs import SERVICE
from luma.models import Settings, PrivacyLevel
from luma.state_machine import StateMachine

ADDRESS = 'AA:BB:CC:DD:EE:FF'


def objects(*, connected=False, trusted=True, powered=True, advertising=True):
    adapter = {'org.bluez.Adapter1': {'Powered': Variant('b', powered)}}
    if advertising:
        adapter[MANAGER] = {}
    return {'/adapter': adapter, '/phone': {'org.bluez.Device1': {
        'Address': Variant('s', ADDRESS), 'Adapter': Variant('o', '/adapter'),
        'Paired': Variant('b', True), 'Bonded': Variant('b', True),
        'Trusted': Variant('b', trusted), 'Connected': Variant('b', connected),
    }}}


def test_wire_contract_is_connectable_ancs_solicitation_not_a_fake_ancs_server():
    advertisement = ANCSSolicitation()
    assert advertisement.Type == 'peripheral'
    assert advertisement.SolicitUUIDs == [SERVICE]
    properties = advertisement.introspect().properties
    assert {p.name: p.signature for p in properties} == {
        'Type': 's', 'SolicitUUIDs': 'as', 'LocalName': 's'}
    assert all(p.access.value == 'read' for p in properties)
    # Calling through the D-Bus dispatcher also exercises the method decorator.
    release = next(m for m in ServiceInterface._get_methods(advertisement) if m.name == 'Release')
    release.fn(advertisement)
    assert advertisement.released


def test_only_disconnected_selected_trusted_bond_can_request_advertising():
    assert reconnect_adapter(objects(), ADDRESS.lower()) == '/adapter'
    for kwargs in ({'connected': True}, {'trusted': False}, {'powered': False}, {'advertising': False}):
        assert reconnect_adapter(objects(**kwargs), ADDRESS) is None
    assert reconnect_adapter(objects(), '') is None
    assert reconnect_adapter(objects(), '11:22:33:44:55:66') is None
    assert StateMachine(Settings()).state.privacy == PrivacyLevel.PRIVATE


def mock_bus(snapshots):
    manager = SimpleNamespace(call_get_managed_objects=AsyncMock(side_effect=snapshots))
    advertiser = SimpleNamespace(call_register_advertisement=AsyncMock(), call_unregister_advertisement=AsyncMock())
    proxy = SimpleNamespace(get_interface=lambda name: advertiser if name == MANAGER else manager)
    bus = SimpleNamespace(introspect=AsyncMock(), get_proxy_object=Mock(return_value=proxy),
                          export=Mock(), unexport=Mock(), disconnect=Mock())
    return bus, advertiser


@pytest.mark.asyncio
async def test_advertisement_follows_disconnect_reconnect_and_forget_without_repairing():
    selection = [ADDRESS]
    bus, advertiser = mock_bus([objects(), objects(connected=True), objects()])
    runtime = ANCSReconnectAdvertising(lambda: selection[0])
    count = 0
    async def pause(_):
        nonlocal count
        count += 1
        if count == 3:
            selection[0] = ''
    await runtime.session(AsyncMock(return_value=bus), pause=pause)
    assert advertiser.call_register_advertisement.await_count == 2
    assert advertiser.call_unregister_advertisement.await_count == 2
    advertiser.call_register_advertisement.assert_awaited_with(PATH, {})
    bus.unexport.assert_called_once()
    bus.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_releases_advertisement_and_bus():
    bus, advertiser = mock_bus([objects()])
    registered = asyncio.Event()
    async def pause(_):
        registered.set()
        await asyncio.Event().wait()
    runtime = ANCSReconnectAdvertising(lambda: ADDRESS)
    task = asyncio.create_task(runtime.session(AsyncMock(return_value=bus), pause=pause))
    await asyncio.wait_for(registered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    advertiser.call_unregister_advertisement.assert_awaited_once_with(PATH)
    bus.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_bluez_release_reregisters_and_registration_failure_never_claims_success():
    bus, advertiser = mock_bus([objects(), objects()])
    selection = [ADDRESS]
    runtime = ANCSReconnectAdvertising(lambda: selection[0])
    count = 0
    async def pause(_):
        nonlocal count
        count += 1
        if count == 1:
            bus.export.call_args.args[1].released = True
        else:
            selection[0] = ''
    await runtime.session(AsyncMock(return_value=bus), pause=pause)
    assert advertiser.call_register_advertisement.await_count == 2
    assert advertiser.call_unregister_advertisement.await_count == 1
    selection[0] = ADDRESS
    bus, advertiser = mock_bus([objects()])
    advertiser.call_register_advertisement.side_effect = RuntimeError('controller unavailable')
    with pytest.raises(RuntimeError):
        await runtime.session(AsyncMock(return_value=bus), pause=AsyncMock())
    assert runtime.status != 'Advertising iPhone notification reconnect'
    bus.unexport.assert_called_once()
    bus.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_worker_recovers_after_bluez_bus_loss_without_stranding_connection_worker(monkeypatch):
    import luma.ancs_advertising as module
    monkeypatch.setattr(module, 'sys', SimpleNamespace(platform='linux'))
    runtime = ANCSReconnectAdvertising(lambda: ADDRESS)
    runtime.session = AsyncMock(side_effect=[RuntimeError('bus lost'), asyncio.CancelledError()])
    pause = AsyncMock()
    with pytest.raises(asyncio.CancelledError):
        await runtime.run(connect=AsyncMock(), pause=pause)
    assert runtime.session.await_count == 2
    pause.assert_awaited_once_with(10)


@pytest.mark.asyncio
async def test_advertisement_properties_and_release_over_real_private_dbus():
    """Exercise the exported wire interface, not only Python property mocks."""
    if not shutil.which('dbus-daemon'):
        pytest.skip('private D-Bus transport requires dbus-daemon')
    from dbus_next.aio import MessageBus
    result = subprocess.run(['dbus-daemon', '--session', '--fork', '--print-address=1',
                             '--print-pid=1'], capture_output=True, text=True, check=True, timeout=5)
    address, pid = result.stdout.strip().splitlines()
    owner = client = None
    try:
        owner = await MessageBus(bus_address=address).connect()
        client = await MessageBus(bus_address=address).connect()
        advertisement = ANCSSolicitation()
        owner.export(PATH, advertisement)
        intro = await client.introspect(owner.unique_name, PATH)
        proxy = client.get_proxy_object(owner.unique_name, PATH, intro)
        properties = await proxy.get_interface('org.freedesktop.DBus.Properties').call_get_all(
            'org.bluez.LEAdvertisement1')
        assert {key: value.value for key, value in properties.items()} == {
            'Type': 'peripheral', 'SolicitUUIDs': [SERVICE], 'LocalName': 'Luma'}
        await proxy.get_interface('org.bluez.LEAdvertisement1').call_release()
        assert advertisement.released
    finally:
        if client:
            client.disconnect()
            await client.wait_for_disconnect()
        if owner:
            owner.disconnect()
            await owner.wait_for_disconnect()
        os.kill(int(pid), signal.SIGTERM)
