import struct
import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from luma.bluetooth_runtime import BluetoothRuntime, BluetoothStatusError, ancs_characteristics, scan_for_paired_phone, trusted_connection, wait_for_ancs, wait_for_trusted_connection
from luma.integrations.ancs import SERVICE, SOURCE, DATA, CONTROL, AttributeResponse, notification, parse_source, request_attributes
from luma.models import PrivacyLevel, Settings
from luma.state_machine import StateMachine


def test_presence_requires_all_bonded_trusted_connection_properties():
    props = {key: True for key in ("Paired", "Bonded", "Trusted", "Connected", "ServicesResolved")}
    assert trusted_connection(props)
    for key in props:
        assert not trusted_connection({**props, key: False})


@pytest.mark.asyncio
async def test_gatt_resolution_can_finish_after_connected_event():
    def snapshot(resolved):
        props = {key: SimpleNamespace(value=True) for key in ("Paired", "Bonded", "Trusted", "Connected")}
        props["ServicesResolved"] = SimpleNamespace(value=resolved)
        return {"/phone": {"org.bluez.Device1": props}}

    manager = SimpleNamespace(call_get_managed_objects=AsyncMock(side_effect=[snapshot(False), snapshot(True)]))
    assert await wait_for_trusted_connection(manager, "/phone", timeout=2) == snapshot(True)
    assert manager.call_get_managed_objects.await_count == 2


@pytest.mark.asyncio
async def test_missing_bond_stays_private_and_reports_fixed_status():
    manager = SimpleNamespace(call_get_managed_objects=AsyncMock(return_value={}))
    with pytest.raises(BluetoothStatusError, match="bond is missing"):
        await wait_for_trusted_connection(manager, "/phone")


@pytest.mark.asyncio
async def test_periodic_discovery_checks_only_saved_phone_and_releases_its_scan():
    def snapshot(connected):
        return {"/phone": {"org.bluez.Device1": {"Connected": SimpleNamespace(value=connected)}},
                "/other": {"org.bluez.Device1": {"Connected": SimpleNamespace(value=True)}}}
    manager = SimpleNamespace(call_get_managed_objects=AsyncMock(side_effect=[snapshot(False), snapshot(True)]))
    adapter = SimpleNamespace(call_set_discovery_filter=AsyncMock(), call_start_discovery=AsyncMock(),
                              call_stop_discovery=AsyncMock())
    pause = AsyncMock()
    assert await scan_for_paired_phone(manager, adapter, "/phone", pause=pause)
    assert manager.call_get_managed_objects.await_count == 2
    adapter.call_start_discovery.assert_awaited_once()
    adapter.call_stop_discovery.assert_awaited_once()
    assert StateMachine(Settings()).state.privacy == PrivacyLevel.PRIVATE


@pytest.mark.asyncio
async def test_discovery_timeout_releases_scan_without_claiming_phone_presence():
    manager = SimpleNamespace(call_get_managed_objects=AsyncMock(return_value={}))
    adapter = SimpleNamespace(call_set_discovery_filter=AsyncMock(), call_start_discovery=AsyncMock(),
                              call_stop_discovery=AsyncMock())
    assert not await scan_for_paired_phone(manager, adapter, "/phone", pause=AsyncMock())
    assert manager.call_get_managed_objects.await_count == 6
    adapter.call_stop_discovery.assert_awaited_once()


@pytest.mark.asyncio
async def test_ancs_reappearing_on_same_connected_link_restores_authorized_path():
    device={key:SimpleNamespace(value=True) for key in ('Paired','Bonded','Trusted','Connected','ServicesResolved')}
    initial={'/phone':{'org.bluez.Device1':device}}
    later={**initial,'/ancs':{'org.bluez.GattService1':{'UUID':SimpleNamespace(value=SERVICE),'Device':SimpleNamespace(value='/phone')}}}
    for name,path in ((SOURCE,'source'),(DATA,'data'),(CONTROL,'control')):
        later['/'+path]={'org.bluez.GattCharacteristic1':{'UUID':SimpleNamespace(value=name),'Service':SimpleNamespace(value='/ancs')}}
    manager=SimpleNamespace(call_get_managed_objects=AsyncMock(return_value=later))
    objects,chars=await wait_for_ancs(manager,'/phone',initial=initial,pause=AsyncMock())
    assert objects is later and {SOURCE,DATA,CONTROL}<=chars.keys()
    assert ancs_characteristics(initial,'/phone')=={}


@pytest.mark.asyncio
async def test_runtime_retries_after_disconnect_then_reopens_only_on_fresh_phone_seen():
    settings=Settings(phone_address='AA:BB:CC:DD:EE:FF',phone_disconnect_grace_seconds=0)
    machine=StateMachine(settings)
    service=SimpleNamespace(settings=settings,state=machine.state,phone_seen=machine.phone_seen,
                            phone_disconnected=machine.phone_disconnected)
    runtime=BluetoothRuntime(service)
    reconnected=asyncio.Event()
    calls=[]
    async def session(address):
        calls.append(address)
        machine.phone_seen()
        if len(calls)==1:return  # The first ANCS session drops.
        reconnected.set()
        await asyncio.Event().wait()
    runtime.session=session
    task=asyncio.create_task(runtime.run(pause=AsyncMock()))
    try:
        await asyncio.wait_for(reconnected.wait(),2)
        assert len(calls)>=2 and machine.state.phone_connected
        assert machine.state.privacy==PrivacyLevel.FULL
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
    assert machine.state.privacy==PrivacyLevel.PRIVATE


def test_disconnect_without_prior_presence_cannot_unlock():
    machine = StateMachine(Settings())
    assert machine.phone_disconnected().privacy == PrivacyLevel.PRIVATE


def test_presence_heartbeat_does_not_undo_explicit_privacy():
    machine = StateMachine(Settings())
    machine.phone_seen()
    machine.force_private()
    assert machine.phone_seen().privacy == PrivacyLevel.PRIVATE


def test_fragmented_attribute_response_and_notification():
    uid = 123
    raw = struct.pack("<BI", 0, uid)
    values = {0: "net.whatsapp.WhatsApp", 1: "Maya", 3: "Incoming call"}
    for key, value in values.items():
        encoded = value.encode()
        raw += struct.pack("<BH", key, len(encoded)) + encoded
    parser = AttributeResponse(uid)
    for byte in raw[:-1]:
        assert parser.feed(bytes([byte])) is None
    decoded = parser.feed(raw[-1:])
    assert decoded == values
    notice = parse_source(struct.pack("<BBBBI", 0, 0, 1, 1, uid))
    result = notification(notice, decoded)
    assert result.app_name == "WhatsApp"
    assert result.category == "incoming-call"
    assert request_attributes(uid).startswith(struct.pack("<BI", 0, uid))


def test_parser_rejects_other_uids_and_oversized_responses():
    with pytest.raises(ValueError):
        AttributeResponse(1).feed(struct.pack("<BI", 0, 2))
    with pytest.raises(ValueError):
        AttributeResponse(1).feed(b"x" * 2049)
    with pytest.raises(ValueError):
        parse_source(b"short")
