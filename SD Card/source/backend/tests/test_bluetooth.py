import struct
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from luma.bluetooth_runtime import BluetoothStatusError, trusted_connection, wait_for_trusted_connection
from luma.integrations.ancs import AttributeResponse, notification, parse_source, request_attributes
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
