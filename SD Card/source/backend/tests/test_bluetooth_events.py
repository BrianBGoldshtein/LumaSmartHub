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
    notify.assert_not_called()


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
    runtime.phone_signal(PHONE,'device',{'Connected':True,'ServicesResolved':True},[],False)
    assert not runtime.companion_presence(guest.id).authorized
    child=runtime.runtime(guest.id)
    child.remote_authorized.begin_bonded(PHONE,'/phone',dict(Address=PHONE,Paired=True,
        Bonded=True,Trusted=True,Connected=True,ServicesResolved=True,Blocked=False))
    child.remote_authorized.heartbeat(PHONE);child.service.phone_seen()
    runtime.phone_signal(PHONE,'ancs',{'Notifying':False},[],False)
    assert runtime.companion_presence(guest.id).authorized
    runtime.phone_signal(PHONE,'device',{'Connected':False},[],False)
    assert not runtime.companion_presence(guest.id).authorized and not child.service.state.phone_connected
