"""Primary administration is separate from radio presence and browser grants."""
from dataclasses import replace

import pytest

from luma.admin_authority import AdminAuthority, AdminDenied, FRESH_SECONDS, LEASE_SECONDS, MAX_LEASES, needs_admin
from luma.companion_auth import PhonePresence
from luma.security import SecurityManager
from luma.storage import Storage


@pytest.fixture
def authority(tmp_path):
    storage = Storage(tmp_path/'luma.db')
    SecurityManager(storage).set_pin('123456')
    clock = [0.0]
    return AdminAuthority(storage, clock=lambda: clock[0]), clock


def test_local_lease_is_origin_bound_ram_only_and_expires(authority):
    admin, clock = authority
    token = admin.unlock_local('123456', 'http://127.0.0.1:8742')
    assert len(token) == 43
    assert admin.require_local(token, 'http://127.0.0.1:8742') == LEASE_SECONDS
    with pytest.raises(AdminDenied):
        AdminAuthority(admin.storage).require_local(token, 'http://127.0.0.1:8742')
    clock[0] = LEASE_SECONDS
    with pytest.raises(AdminDenied):
        admin.require_local(token, 'http://127.0.0.1:8742')
    assert not admin.leases


def test_wrong_origin_cannot_use_or_keep_lease(authority):
    admin, _ = authority
    token = admin.unlock_local('123456', 'http://127.0.0.1:8742')
    with pytest.raises(AdminDenied):
        admin.require_local(token, 'https://other.test')
    assert not admin.leases


def test_fresh_pin_required_without_revoking_ordinary_lease(authority):
    admin, clock = authority
    token = admin.unlock_local('123456', 'wall')
    clock[0] = FRESH_SECONDS
    with pytest.raises(AdminDenied) as error:
        admin.require_local(token, 'wall', fresh=True)
    assert error.value.fresh
    assert admin.require_local(token, 'wall') == LEASE_SECONDS-FRESH_SECONDS
    replacement = admin.unlock_local('123456', 'wall', previous=token)
    assert admin.require_local(replacement, 'wall', fresh=True) == LEASE_SECONDS
    with pytest.raises(AdminDenied): admin.require_local(token, 'wall')


def test_pin_change_revokes_all_existing_authority(authority):
    admin, _ = authority
    token = admin.unlock_local('123456', 'wall')
    SecurityManager(admin.storage).set_pin('456789')
    with pytest.raises(AdminDenied): admin.require_local(token, 'wall')


def test_remote_bound_to_primary_exact_live_session_and_device(authority):
    admin, _ = authority
    phone = PhonePresence('AA:BB:CC:DD:EE:01', True, 'generation-1')
    admin.unlock_remote('123456', 'browser', phone)
    assert admin.require_remote('browser', phone) == LEASE_SECONDS
    for other in [replace(phone, generation=2), replace(phone, authorized=False),
                  replace(phone, profile_id='guest', role='secondary')]:
        with pytest.raises(AdminDenied): admin.require_remote('browser', other)
    with pytest.raises(AdminDenied): admin.require_remote('other-browser', phone)


def test_guest_knowing_primary_pin_cannot_promote_and_does_not_burn_pin_attempts(authority):
    admin, _ = authority
    guest = PhonePresence('AA:BB:CC:DD:EE:02', True, 'generation-1', 'guest', 'secondary')
    for _ in range(6):
        with pytest.raises(AdminDenied): admin.unlock_remote('000000', 'guest-browser', guest)
    token = admin.unlock_local('123456', 'wall')
    assert admin.require_local(token, 'wall') == LEASE_SECONDS


def test_capacity_does_not_evict_healthy_owner(authority):
    admin, clock = authority
    first = admin.unlock_local('123456', 'wall')
    for _ in range(MAX_LEASES-1): admin.unlock_local('123456', 'wall')
    with pytest.raises(AdminDenied): admin.unlock_local('123456', 'wall')
    assert admin.require_local(first, 'wall') == LEASE_SECONDS
    clock[0] = LEASE_SECONDS
    assert admin.unlock_local('123456', 'wall')
    assert len(admin.leases) == 1


@pytest.mark.parametrize('method,path,command,expected', [
    ('POST','/api/v1/commands','set_theme',True),
    ('POST','/api/v1/voice/command','set_volume',True),
    ('POST','/api/v1/shortcut-command','run_remote_scene',True),
    ('POST','/api/v1/commands','start_timer',False),
    ('GET','/api/v1/settings',None,True),
    ('HEAD','/api/v1/google/calendars',None,True),
    ('GET','/api/v1/state',None,False),
    ('GET','/api/v1/updates/status',None,False),
    ('POST','/api/v1/updates/install',None,True),
    ('POST','/api/v1/device/timer-chime',None,False),
    ('POST','/api/v1/voice/phase',None,False),
    ('POST','/api/v1/future-management-endpoint',None,True),
])
def test_global_mutations_fail_closed_and_workers_and_timers_remain_available(method,path,command,expected):
    assert needs_admin(method,path,command) is expected
