"""Signal hints wake verification, never bypass consent or another user's lease."""
from unittest.mock import Mock

import pytest
from dbus_next import Message,MessageType,Variant

from luma.bluetooth_events import PhoneSignalMonitor,DEVICE,GATT,CHAR
from luma.integrations.ancs import SERVICE,SOURCE

PHONE='AA:BB:CC:DD:EE:FF'


def monitor():
    notify=Mock()
    observer=PhoneSignalMonitor(notify,Mock());observer.owner=':1.20'
    observer.remember('/phone',{DEVICE:{'Address':Variant('s',PHONE)}})
    observer.remember('/phone/service',{GATT:{'Device':Variant('o','/phone'),'UUID':Variant('s',SERVICE)}})
    observer.remember('/phone/source',{CHAR:{'Service':Variant('o','/phone/service'),'UUID':Variant('s',SOURCE)}})
    return observer,notify


def changed(sender=':1.20',path='/phone',interface=DEVICE,values=None,invalidated=None):
    return Message(message_type=MessageType.SIGNAL,sender=sender,path=path,
        interface='org.freedesktop.DBus.Properties',member='PropertiesChanged',signature='sa{sv}as',
        body=[interface,values or {},invalidated or []])


@pytest.mark.parametrize('sender',[None,':1.99','org.bluez'])
def test_forged_or_unowned_signal_cannot_wake_or_revoke(sender):
    observer,notify=monitor()
    observer.handle(changed(sender=sender,values={'Connected':Variant('b',True)}))
    assert notify.call_count == 0


def test_selected_signal_is_a_hint_and_notification_content_is_not_cached():
    observer,notify=monitor()
    observer.handle(changed(values={'Connected':Variant('b',True),'Name':Variant('s','Private phone')}))
    notify.assert_called_once_with(PHONE,'device',{'Connected':True},[],False)
    assert 'Name' not in observer.objects['/phone'][DEVICE]
    notify.reset_mock()
    observer.handle(changed(path='/phone/source',interface=CHAR,values={'Value':Variant('ay',b'private')}))
    notify.assert_not_called()
    assert 'Value' not in observer.objects['/phone/source'][CHAR]
    observer.handle(changed(path='/phone/source',interface=CHAR,values={'Notifying':Variant('b',False)}))
    notify.assert_called_once_with(PHONE,'ancs',{'Notifying':False},[],False)


def test_radio_noise_burst_never_calls_the_presence_receiver():
    observer,notify=monitor()
    for index in range(2000):
        observer.handle(changed(values={'RSSI':Variant('n',-50-index%20),
            'ManufacturerData':Variant('a{qv}',{})}))
    assert notify.call_count == 0


def test_signal_callback_does_not_query_profiles_for_unregistered_or_known_phones(tmp_path):
    from luma.api import create_app
    app=create_app(data_dir=tmp_path)
    runtime=app.state.bluetooth
    app.state.luma.update_settings({'phone_address':PHONE})
    runtime.refresh_signal_users()
    child=runtime.runtime('primary')
    app.state.profiles.by_phone=Mock(side_effect=AssertionError('Database lookup in D-Bus callback'))
    app.state.profiles.get=Mock(side_effect=AssertionError('Profile validation in D-Bus callback'))
    runtime.phone_signal('AA:BB:CC:DD:EE:99','device',{'Connected':True},[],False)
    runtime.phone_signal(PHONE,'device',{'Connected':True},[],False)
    assert child.change_event.is_set()
    assert not child.remote_authorized.generation


@pytest.mark.parametrize('remove',[False,True])
def test_stale_signal_cache_cannot_restore_replaced_or_removed_user(tmp_path,remove):
    from luma.api import create_app
    app=create_app(data_dir=tmp_path)
    runtime=app.state.bluetooth
    guest=app.state.profiles.create_secondary('Alex')
    app.state.profiles.bind_phone(guest.id,PHONE)
    child=runtime.runtime(guest.id)
    runtime.refresh_signal_users()
    child.remote_authorized.begin_bonded(PHONE,'/phone',dict(Address=PHONE,Paired=True,
        Bonded=True,Trusted=True,Connected=True,ServicesResolved=True,Blocked=False))
    child.remote_authorized.heartbeat(PHONE);child.service.phone_seen()
    assert runtime.companion_presence(guest.id).authorized
    if remove:
        app.state.profiles.remove(guest.id)
    else:
        app.state.profiles.bind_phone(guest.id,'AA:BB:CC:DD:EE:99')
    # Hints can race the one-second registry refresh. Authority always checks
    # the current selected phone/profile, never this bounded dispatch cache.
    runtime.phone_signal(PHONE,'device',{'Connected':True,'ServicesResolved':True},[],False)
    assert not runtime.companion_presence(guest.id).authorized
    assert guest.id not in runtime.present_ids()
    runtime.refresh_signal_users()
    child.change_event.clear()
    runtime.phone_signal(PHONE,'device',{'Connected':True},[],False)
    assert not child.change_event.is_set()


def test_interfaces_removed_keeps_original_phone_identity_for_revocation():
    observer,notify=monitor()
    observer.handle(Message(message_type=MessageType.SIGNAL,sender=':1.20',path='/',
        interface='org.freedesktop.DBus.ObjectManager',member='InterfacesRemoved',signature='oas',
        body=['/phone/source',[CHAR]]))
    notify.assert_called_once_with(PHONE,'ancs',{},[],True)


def test_raw_connection_and_secondary_notification_signals_never_grant_authority(tmp_path):
    from luma.api import create_app
    app=create_app(data_dir=tmp_path)
    runtime=app.state.bluetooth
    guest=app.state.profiles.create_secondary('Alex')
    app.state.profiles.bind_phone(guest.id,PHONE)
    runtime.refresh_signal_users()
    child=runtime.runtime(guest.id)
    runtime.phone_signal(PHONE,'device',{'Connected':True,'ServicesResolved':True},[],False)
    assert not runtime.companion_presence(guest.id).authorized
    child.remote_authorized.begin_bonded(PHONE,'/phone',dict(Address=PHONE,Paired=True,
        Bonded=True,Trusted=True,Connected=True,ServicesResolved=True,Blocked=False))
    child.remote_authorized.heartbeat(PHONE);child.service.phone_seen()
    runtime.phone_signal(PHONE,'ancs',{'Notifying':False},[],False)
    assert runtime.companion_presence(guest.id).authorized
    runtime.phone_signal(PHONE,'device',{'Connected':False},[],False)
    assert not runtime.companion_presence(guest.id).authorized and not child.service.state.phone_connected
