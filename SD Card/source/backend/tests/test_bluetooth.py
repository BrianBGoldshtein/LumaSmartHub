import struct
import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from luma.bluetooth_runtime import BluetoothRuntime, BluetoothStatusError, ancs_characteristics, connect_paired_phone, prefer_le_bearer, recover_stalled_services, scan_for_paired_phone, subscribe_ancs, trusted_connection, wait_for_ancs, wait_for_trusted_connection
from luma.integrations.ancs import SERVICE, SOURCE, DATA, CONTROL, AttributeResponse, notification, parse_source, request_attributes
from luma.models import PrivacyLevel, Settings
from luma.state_machine import StateMachine


def test_presence_requires_all_bonded_trusted_connection_properties():
    props = {key: True for key in ("Paired", "Bonded", "Trusted", "Connected", "ServicesResolved")}
    assert trusted_connection(props)
    for key in props:
        assert not trusted_connection({**props, key: False})


def paired_snapshot(connected=False):
    props = {key: SimpleNamespace(value=True) for key in ('Paired', 'Bonded', 'Trusted')}
    props['Connected'] = SimpleNamespace(value=connected)
    return {'/phone': {'org.bluez.Device1': props}}


@pytest.mark.asyncio
async def test_pending_connect_timeout_cancels_bluez_not_just_python_future():
    async def never_reply():
        await asyncio.Event().wait()
    manager = SimpleNamespace(call_get_managed_objects=AsyncMock(return_value=paired_snapshot()))
    device = SimpleNamespace(call_connect=AsyncMock(side_effect=never_reply), call_disconnect=AsyncMock())
    with pytest.raises(BluetoothStatusError, match='did not finish'):
        await connect_paired_phone(manager, device, '/phone', timeout=.01)
    device.call_connect.assert_awaited_once()
    device.call_disconnect.assert_awaited_once()
    assert StateMachine(Settings()).state.privacy == PrivacyLevel.PRIVATE


@pytest.mark.asyncio
async def test_completed_manual_link_wins_over_connect_error_without_disconnect():
    manager = SimpleNamespace(call_get_managed_objects=AsyncMock(
        side_effect=[paired_snapshot(), paired_snapshot(True)]))
    device = SimpleNamespace(call_connect=AsyncMock(side_effect=RuntimeError('InProgress')),
                             call_disconnect=AsyncMock())
    await connect_paired_phone(manager, device, '/phone')
    device.call_disconnect.assert_not_awaited()


@pytest.mark.asyncio
async def test_already_connected_phone_never_gets_connect_or_disconnect_request():
    manager = SimpleNamespace(call_get_managed_objects=AsyncMock(return_value=paired_snapshot(True)))
    device = SimpleNamespace(call_connect=AsyncMock(), call_disconnect=AsyncMock())
    await connect_paired_phone(manager, device, '/phone')
    device.call_connect.assert_not_awaited()
    device.call_disconnect.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_request_cannot_cancel_after_selection_or_bond_changes():
    selected = [True]
    async def fail():
        selected[0] = False
        raise RuntimeError('connect failed')
    manager = SimpleNamespace(call_get_managed_objects=AsyncMock(return_value=paired_snapshot()))
    device = SimpleNamespace(call_connect=AsyncMock(side_effect=fail), call_disconnect=AsyncMock())
    with pytest.raises(BluetoothStatusError):
        await connect_paired_phone(manager, device, '/phone', address_is_current=lambda: selected[0])
    device.call_disconnect.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_worker_cleans_up_selected_pending_radio_request():
    started = asyncio.Event()
    async def pending():
        started.set()
        await asyncio.Event().wait()
    manager = SimpleNamespace(call_get_managed_objects=AsyncMock(return_value=paired_snapshot()))
    device = SimpleNamespace(call_connect=AsyncMock(side_effect=pending), call_disconnect=AsyncMock())
    task = asyncio.create_task(connect_paired_phone(manager, device, '/phone'))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    device.call_disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_explicit_scan_disables_competing_bluez_autoconnect():
    manager = SimpleNamespace(call_get_managed_objects=AsyncMock(return_value=paired_snapshot()))
    adapter = SimpleNamespace(call_set_discovery_filter=AsyncMock(), call_start_discovery=AsyncMock(),
                              call_stop_discovery=AsyncMock())
    connect = AsyncMock()
    await scan_for_paired_phone(manager, adapter, '/phone', phone_address='AA:BB:CC:DD:EE:FF',
                                pause=AsyncMock(), connect=connect)
    assert adapter.call_set_discovery_filter.await_args.args[0]['AutoConnect'].value is False
    connect.assert_awaited_once()
    adapter.call_stop_discovery.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('name', [
    'org.bluez.Error.InProgress', 'org.bluez.Error.Failed',
    'org.bluez.Error.NotReady', 'org.bluez.Error.AlreadyConnected',
])
async def test_terminal_connect_rejection_never_cancels_someone_elses_operation(name):
    from dbus_next import DBusError
    manager = SimpleNamespace(call_get_managed_objects=AsyncMock(return_value=paired_snapshot()))
    device = SimpleNamespace(call_connect=AsyncMock(side_effect=DBusError(name, 'PRIVATE_PHONE_TEXT')),
                             call_disconnect=AsyncMock())
    with pytest.raises(BluetoothStatusError, match='did not finish') as caught:
        await connect_paired_phone(manager, device, '/phone')
    assert 'PRIVATE_PHONE_TEXT' not in str(caught.value)
    device.call_disconnect.assert_not_awaited()
    assert all(manager.call_get_managed_objects.return_value['/phone']['org.bluez.Device1'][key].value
               for key in ('Paired', 'Bonded', 'Trusted'))


@pytest.mark.asyncio
async def test_runtime_scan_connect_failure_does_not_immediately_issue_second_connect(monkeypatch):
    import dbus_next.aio
    import luma.bluetooth_runtime as module
    objects = {**paired_snapshot(), '/adapter': {'org.bluez.Adapter1': {}}}
    objects['/phone']['org.bluez.Device1']['Address'] = SimpleNamespace(value='AA:BB:CC:DD:EE:FF')
    manager = SimpleNamespace(call_get_managed_objects=AsyncMock(return_value=objects))
    adapter = SimpleNamespace(call_set_discovery_filter=AsyncMock(), call_start_discovery=AsyncMock(),
                              call_stop_discovery=AsyncMock())
    device = SimpleNamespace(call_connect=AsyncMock(side_effect=asyncio.TimeoutError()),
                             call_disconnect=AsyncMock())
    interfaces = {'org.freedesktop.DBus.ObjectManager': manager, 'org.bluez.Device1': device,
                  'org.bluez.Adapter1': adapter, 'org.freedesktop.DBus.Properties': SimpleNamespace()}
    bus = SimpleNamespace(connect=AsyncMock(), introspect=AsyncMock(), disconnect=lambda: None,
                          get_proxy_object=lambda *args: SimpleNamespace(
                              get_interface=lambda name: interfaces[name]))
    monkeypatch.setattr(dbus_next.aio, 'MessageBus', lambda **kwargs: bus)
    real_scan = module.scan_for_paired_phone
    async def quick_scan(*args, **kwargs):
        return await real_scan(*args, **kwargs, pause=AsyncMock())
    monkeypatch.setattr(module, 'scan_for_paired_phone', quick_scan)
    runtime = BluetoothRuntime(SimpleNamespace(settings=Settings(phone_address='AA:BB:CC:DD:EE:FF')))
    with pytest.raises(BluetoothStatusError, match='did not finish'):
        await runtime.session('AA:BB:CC:DD:EE:FF')
    assert runtime.reconnect_attempts == 1
    device.call_connect.assert_awaited_once()
    device.call_disconnect.assert_awaited_once()
    adapter.call_stop_discovery.assert_awaited_once()


@pytest.mark.asyncio
async def test_explicit_le_connect_runs_before_scan_stops_and_is_not_presence():
    props = {key: SimpleNamespace(value=True) for key in ('Paired', 'Bonded', 'Trusted')}
    props['Connected'] = SimpleNamespace(value=False)
    manager = SimpleNamespace(call_get_managed_objects=AsyncMock(return_value={
        '/phone': {'org.bluez.Device1': props}}))
    adapter = SimpleNamespace(call_set_discovery_filter=AsyncMock(), call_start_discovery=AsyncMock(),
                              call_stop_discovery=AsyncMock())
    async def connect():
        adapter.call_start_discovery.assert_awaited_once()
        adapter.call_stop_discovery.assert_not_awaited()
    assert await scan_for_paired_phone(manager, adapter, '/phone', pause=AsyncMock(), connect=connect)
    adapter.call_stop_discovery.assert_awaited_once()
    assert StateMachine(Settings()).state.privacy == PrivacyLevel.PRIVATE


@pytest.mark.asyncio
async def test_scan_cancel_or_selection_change_never_connects_or_leaves_discovery_active():
    manager = SimpleNamespace(call_get_managed_objects=AsyncMock(return_value={}))
    adapter = SimpleNamespace(call_set_discovery_filter=AsyncMock(), call_start_discovery=AsyncMock(),
                              call_stop_discovery=AsyncMock())
    connect = AsyncMock()
    assert not await scan_for_paired_phone(manager, adapter, '/phone', pause=AsyncMock(), connect=connect,
                                           address_is_current=lambda: False)
    connect.assert_not_awaited()
    adapter.call_stop_discovery.assert_awaited_once()
    adapter.call_stop_discovery.reset_mock()
    with pytest.raises(asyncio.CancelledError):
        await scan_for_paired_phone(manager, adapter, '/phone',
            pause=AsyncMock(side_effect=asyncio.CancelledError()), connect=connect)
    adapter.call_stop_discovery.assert_awaited_once()
    connect.assert_not_awaited()


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
async def test_stalled_bluez_object_query_times_out_instead_of_blocking_reconnect():
    async def no_reply():
        await asyncio.Event().wait()

    manager = SimpleNamespace(call_get_managed_objects=AsyncMock(side_effect=no_reply))
    with pytest.raises(asyncio.TimeoutError):
        await wait_for_trusted_connection(manager, "/phone", query_timeout=0.02)
    manager.call_get_managed_objects.assert_awaited_once()


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
    assert manager.call_get_managed_objects.await_count == 12
    adapter.call_stop_discovery.assert_awaited_once()


@pytest.mark.asyncio
async def test_selected_bonded_phone_gets_scoped_le_autoconnect_scan():
    props={"Connected":SimpleNamespace(value=True)}
    manager=SimpleNamespace(call_get_managed_objects=AsyncMock(return_value={"/phone":{"org.bluez.Device1":props}}))
    adapter=SimpleNamespace(call_set_discovery_filter=AsyncMock(),call_start_discovery=AsyncMock(),
                            call_stop_discovery=AsyncMock())
    assert await scan_for_paired_phone(manager,adapter,"/phone",
                                       phone_address="AA:BB:CC:DD:EE:FF",pause=AsyncMock())
    selected=adapter.call_set_discovery_filter.await_args.args[0]
    assert selected['Transport'].value=='le'
    assert selected['Pattern'].value=='AA:BB:CC:DD:EE:FF'
    assert selected['AutoConnect'].value is True
    adapter.call_stop_discovery.assert_awaited_once()


@pytest.mark.asyncio
async def test_unsupported_autoconnect_falls_back_to_plain_le_discovery():
    manager=SimpleNamespace(call_get_managed_objects=AsyncMock(return_value={}))
    adapter=SimpleNamespace(call_set_discovery_filter=AsyncMock(side_effect=[RuntimeError('unsupported'),None]),
                            call_start_discovery=AsyncMock(),call_stop_discovery=AsyncMock())
    assert not await scan_for_paired_phone(manager,adapter,"/phone",
                                           phone_address="AA:BB:CC:DD:EE:FF",pause=AsyncMock())
    assert adapter.call_set_discovery_filter.await_count==2
    fallback=adapter.call_set_discovery_filter.await_args.args[0]
    assert fallback['Transport'].value=='le' and 'AutoConnect' not in fallback
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
async def test_ancs_source_alone_is_enough_to_try_authorized_subscription():
    # Apple defines Data Source and Control Point as optional. The runtime
    # still cannot unlock until Notification Source StartNotify succeeds.
    device={key:SimpleNamespace(value=True) for key in ('Paired','Bonded','Trusted','Connected')}
    device['ServicesResolved']=SimpleNamespace(value=False)
    objects={'/phone':{'org.bluez.Device1':device},
             '/ancs':{'org.bluez.GattService1':{'UUID':SimpleNamespace(value=SERVICE),'Device':SimpleNamespace(value='/phone')}},
             '/source':{'org.bluez.GattCharacteristic1':{'UUID':SimpleNamespace(value=SOURCE),'Service':SimpleNamespace(value='/ancs')}}}
    manager=SimpleNamespace(call_get_managed_objects=AsyncMock(return_value=objects))
    assert await wait_for_trusted_connection(manager,'/phone') is objects
    _,chars=await wait_for_ancs(manager,'/phone',initial=objects)
    assert chars == {SOURCE:'/source'}


@pytest.mark.asyncio
async def test_optional_data_subscription_failure_keeps_source_authorized_without_details():
    source=SimpleNamespace(call_start_notify=AsyncMock())
    data=SimpleNamespace(call_start_notify=AsyncMock(side_effect=RuntimeError('no optional data')))
    assert not await subscribe_ancs(source,data)
    source.call_start_notify.assert_awaited_once()
    data.call_start_notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_source_authorization_failure_never_uses_optional_data():
    source=SimpleNamespace(call_start_notify=AsyncMock(side_effect=RuntimeError('not authorized')))
    data=SimpleNamespace(call_start_notify=AsyncMock())
    with pytest.raises(BluetoothStatusError,match='authorization'):
        await subscribe_ancs(source,data)
    data.call_start_notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_stalled_bonded_service_recovers_without_forgetting_phone():
    def snapshot(connected):
        props={key:SimpleNamespace(value=True) for key in ('Paired','Bonded','Trusted')}
        props['Connected']=SimpleNamespace(value=connected)
        props['ServicesResolved']=SimpleNamespace(value=False)
        return {'/phone':{'org.bluez.Device1':props}}
    manager=SimpleNamespace(call_get_managed_objects=AsyncMock(side_effect=[snapshot(True),snapshot(False),snapshot(False),snapshot(False)]))
    device=SimpleNamespace(call_disconnect=AsyncMock(),call_connect=AsyncMock())
    properties=SimpleNamespace(call_set=AsyncMock())
    await recover_stalled_services(manager,device,properties,'/phone',pause=AsyncMock())
    device.call_disconnect.assert_awaited_once()
    device.call_connect.assert_awaited_once()
    properties.call_set.assert_not_awaited()


@pytest.mark.asyncio
async def test_recovery_prefers_le_bearer_when_bluez_exposes_it():
    def snapshot(connected, bearer="last-used"):
        props={key:SimpleNamespace(value=True) for key in ('Paired','Bonded','Trusted')}
        props['Connected']=SimpleNamespace(value=connected)
        props['PreferredBearer']=SimpleNamespace(value=bearer)
        return {'/phone':{'org.bluez.Device1':props}}
    manager=SimpleNamespace(call_get_managed_objects=AsyncMock(side_effect=[snapshot(True),snapshot(False),snapshot(False),snapshot(False)]))
    device=SimpleNamespace(call_disconnect=AsyncMock(),call_connect=AsyncMock())
    properties=SimpleNamespace(call_set=AsyncMock())
    await recover_stalled_services(manager,device,properties,'/phone',pause=AsyncMock())
    assert properties.call_set.await_count == 1
    name,key,value=properties.call_set.await_args.args
    assert (name,key,value.value) == ('org.bluez.Device1','PreferredBearer','le')
    device.call_connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_already_preferred_le_is_left_unchanged():
    properties=SimpleNamespace(call_set=AsyncMock())
    assert not await prefer_le_bearer(properties, {'PreferredBearer':'le'})
    properties.call_set.assert_not_awaited()


@pytest.mark.asyncio
async def test_runtime_repairs_stalled_services_once_per_cooldown(monkeypatch):
    import luma.bluetooth_runtime as bluetooth_module
    settings=Settings(phone_address='AA:BB:CC:DD:EE:FF')
    runtime=BluetoothRuntime(SimpleNamespace(settings=settings))
    repair=AsyncMock()
    monkeypatch.setattr(bluetooth_module,'recover_stalled_services',repair)
    await runtime.refresh_phone_services('manager','device','properties','/phone','adapter',settings.phone_address)
    repair.assert_awaited_once()
    assert runtime.service_recovery_attempts == 1
    assert runtime.last_service_recovery_at
    with pytest.raises(BluetoothStatusError,match='retry automatically'):
        await runtime.refresh_phone_services('manager','device','properties','/phone','adapter',settings.phone_address)
    repair.assert_awaited_once()
    settings.phone_address='11:22:33:44:55:66'
    runtime.last_service_recovery -= 301
    with pytest.raises(BluetoothStatusError,match='retry automatically'):
        await runtime.refresh_phone_services('manager','device','properties','/phone','adapter','AA:BB:CC:DD:EE:FF')
    repair.assert_awaited_once()


@pytest.mark.asyncio
async def test_service_recovery_scans_le_and_accepts_phone_initiated_reconnect():
    def snapshot(connected):
        props={key:SimpleNamespace(value=True) for key in ('Paired','Bonded','Trusted')}
        props['Connected']=SimpleNamespace(value=connected)
        props['ServicesResolved']=SimpleNamespace(value=False)
        return {'/phone':{'org.bluez.Device1':props}}
    manager=SimpleNamespace(call_get_managed_objects=AsyncMock(side_effect=[
        snapshot(True),snapshot(False),snapshot(False),snapshot(True),snapshot(True)]))
    device=SimpleNamespace(call_disconnect=AsyncMock(),call_connect=AsyncMock())
    adapter=SimpleNamespace(call_set_discovery_filter=AsyncMock(),call_start_discovery=AsyncMock(),
                            call_stop_discovery=AsyncMock())
    await recover_stalled_services(manager,device,SimpleNamespace(call_set=AsyncMock()),
                                   '/phone',adapter=adapter,pause=AsyncMock())
    adapter.call_start_discovery.assert_awaited_once()
    adapter.call_stop_discovery.assert_awaited_once()
    device.call_connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_fast_phone_reconnect_with_ancs_does_not_look_like_failed_reset():
    def snapshot(with_ancs):
        props={key:SimpleNamespace(value=True) for key in ('Paired','Bonded','Trusted','Connected')}
        objects={'/phone':{'org.bluez.Device1':props}}
        if with_ancs:
            objects['/ancs']={'org.bluez.GattService1':{'UUID':SimpleNamespace(value=SERVICE),
                                                     'Device':SimpleNamespace(value='/phone')}}
            objects['/source']={'org.bluez.GattCharacteristic1':{
                'UUID':SimpleNamespace(value=SOURCE),'Service':SimpleNamespace(value='/ancs')}}
        return objects
    manager=SimpleNamespace(call_get_managed_objects=AsyncMock(side_effect=[snapshot(False),snapshot(True)]))
    device=SimpleNamespace(call_disconnect=AsyncMock(),call_connect=AsyncMock())
    await recover_stalled_services(manager,device,SimpleNamespace(call_set=AsyncMock()),
                                   '/phone',pause=AsyncMock())
    device.call_disconnect.assert_awaited_once()
    device.call_connect.assert_not_awaited()
    # An exposed source is only an opportunity to subscribe, not presence.
    assert StateMachine(Settings()).state.privacy == PrivacyLevel.PRIVATE


@pytest.mark.asyncio
async def test_phone_initiated_disconnect_race_preserves_bond_and_reconnects():
    def snapshot(connected):
        props={key:SimpleNamespace(value=True) for key in ('Paired','Bonded','Trusted')}
        props['Connected']=SimpleNamespace(value=connected)
        return {'/phone':{'org.bluez.Device1':props}}
    manager=SimpleNamespace(call_get_managed_objects=AsyncMock(side_effect=[
        snapshot(True),snapshot(False),snapshot(False),snapshot(False),snapshot(False)]))
    device=SimpleNamespace(call_disconnect=AsyncMock(side_effect=RuntimeError('already disconnected')),
                           call_connect=AsyncMock())
    await recover_stalled_services(manager,device,SimpleNamespace(call_set=AsyncMock()),
                                   '/phone',pause=AsyncMock())
    device.call_connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_stalled_service_recovery_refuses_phone_selection_change():
    props={key:SimpleNamespace(value=True) for key in ('Paired','Bonded','Trusted','Connected')}
    manager=SimpleNamespace(call_get_managed_objects=AsyncMock(return_value={'/phone':{'org.bluez.Device1':props}}))
    device=SimpleNamespace(call_disconnect=AsyncMock(),call_connect=AsyncMock())
    with pytest.raises(BluetoothStatusError,match='changed'):
        await recover_stalled_services(manager,device,SimpleNamespace(),'/phone',address_is_current=lambda:False)
    device.call_disconnect.assert_not_awaited()


@pytest.mark.asyncio
async def test_runtime_retries_after_disconnect_then_reopens_only_on_fresh_phone_seen(monkeypatch):
    import luma.bluetooth_runtime as bluetooth_module
    monkeypatch.setattr(bluetooth_module, 'sys', SimpleNamespace(platform='linux'))
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
