from types import SimpleNamespace

import pytest

from luma.companion_presence import AuthorizedPhoneSession

PHONE = 'AA:BB:CC:DD:EE:FF'


def ready():
    clock = [100.0]
    lease = AuthorizedPhoneSession(clock=lambda: clock[0])
    lease.begin(PHONE, '/phone', '/phone/source')
    lease.heartbeat(PHONE)
    return lease, clock


def test_begin_requires_a_live_heartbeat_not_link_or_pin_privacy():
    lease = AuthorizedPhoneSession()
    assert not lease.snapshot(PHONE, phone_connected=True).authorized
    lease.begin(PHONE, '/phone', '/phone/source')
    assert not lease.snapshot(PHONE, phone_connected=True).authorized
    lease.heartbeat(PHONE)
    assert lease.snapshot(PHONE, phone_connected=True).authorized
    assert not lease.snapshot(PHONE, phone_connected=False).authorized


def test_generation_is_per_subscription_not_per_heartbeat():
    lease, clock = ready()
    old = lease.snapshot(PHONE, phone_connected=True).generation
    clock[0] += 5
    lease.heartbeat(PHONE)
    assert lease.snapshot(PHONE, phone_connected=True).generation == old
    lease.clear()
    lease.begin(PHONE, '/phone', '/phone/source')
    lease.heartbeat(PHONE)
    assert lease.snapshot(PHONE, phone_connected=True).generation != old


@pytest.mark.parametrize('field', ['Paired', 'Bonded', 'Trusted', 'Connected'])
@pytest.mark.parametrize('invalidated', [False, True])
def test_trust_loss_signal_immediately_revokes_even_before_poll(field, invalidated):
    lease, _ = ready()
    lease.properties_changed('org.bluez.Device1', {} if invalidated else {field:SimpleNamespace(value=False)},
                             [field] if invalidated else [])
    lease.heartbeat(PHONE)  # Cannot reauthorize a stale subscription.
    assert not lease.snapshot(PHONE, phone_connected=True).authorized


@pytest.mark.parametrize('path,interfaces', [('/phone',['org.bluez.Device1']),
    ('/phone/source',['org.bluez.GattCharacteristic1'])])
def test_device_or_source_removal_revokes_immediately(path, interfaces):
    lease, _ = ready()
    lease.interfaces_removed(path, interfaces)
    assert not lease.snapshot(PHONE, phone_connected=True).authorized


def test_unrelated_signals_do_not_drop_authorized_session():
    lease, _ = ready()
    lease.properties_changed('org.bluez.Device1', {'Name':'private phone name'}, [])
    lease.properties_changed('org.bluez.GattCharacteristic1', {'Connected':False}, [])
    lease.interfaces_removed('/another/phone', ['org.bluez.Device1'])
    assert lease.snapshot(PHONE, phone_connected=True).authorized


@pytest.mark.parametrize('invalidated', [False, True])
def test_source_subscription_loss_revokes_remote_authority(invalidated):
    lease, _ = ready()
    lease.source_properties_changed('org.bluez.GattCharacteristic1',
        {} if invalidated else {'Notifying':SimpleNamespace(value=False)}, ['Notifying'] if invalidated else [])
    assert not lease.snapshot(PHONE, phone_connected=True).authorized


def test_selection_change_stale_check_and_clock_anomaly_fail_closed():
    lease, clock = ready()
    assert not lease.snapshot('11:22:33:44:55:66', phone_connected=True).authorized
    clock[0] += 15.01
    assert not lease.snapshot(PHONE, phone_connected=True).authorized
    lease.heartbeat(PHONE)
    assert lease.generation == ''
    lease.begin(PHONE, '/phone', '/phone/source')
    lease.heartbeat(PHONE)
    clock[0] = 99
    assert not lease.snapshot(PHONE, phone_connected=True).authorized


def test_restore_revokes_remote_browser_grants_but_preserves_google_and_settings(tmp_path):
    from luma.storage import Storage
    from luma.companion_auth import GRANTS_KEY
    storage = Storage(tmp_path / 'live.db')
    storage.set_secret(GRANTS_KEY, 'old authorization')
    storage.set_secret('companion_google_oauth_state_v1', 'old pending attempt')
    storage.set_secret('google_credentials', 'saved grant')
    before = storage.load_settings()
    backup = storage.backup(tmp_path / 'snapshot.db')
    storage.restore(backup)
    assert storage.get_secret(GRANTS_KEY) is None
    assert storage.get_secret('companion_google_oauth_state_v1') is None
    assert storage.get_secret('google_credentials') == 'saved grant'
    assert storage.load_settings() == before
    assert list(tmp_path.glob('.luma-restore-*')) == []
