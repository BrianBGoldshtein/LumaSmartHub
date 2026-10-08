"""Signed account authority with synthetic phones; no owner accounts/radio."""
from dataclasses import replace
import hashlib
import json

import pytest

from luma.companion_auth import CompanionAuth, CompanionDenied, GRANTS_KEY as LEGACY_KEY, PhonePresence
from luma.profiles import ProfileRepository, GRANTS_KEY, PRIMARY_ID
from luma.security import SecurityManager
from luma.storage import Storage
from test_companion_auth import ORIGIN, IDENTITY, PATH, enroll, key_pair, sign, enrollment_message, request_message


@pytest.fixture
def rig(tmp_path):
    storage = Storage(tmp_path/'luma.db')
    profiles = ProfileRepository(storage)
    SecurityManager(storage).set_pin('123456')
    profiles.bind_phone(PRIMARY_ID, 'AA:BB:CC:DD:EE:01')
    users = [profiles.get(PRIMARY_ID)]
    for number in range(2, 6):
        user = profiles.create_secondary(f'Guest {number}')
        users.append(profiles.bind_phone(user.id, f'AA:BB:CC:DD:EE:0{number}'))
    state = {user.id: PhonePresence(user.phone_address, True, f'session-{index}')
             for index, user in enumerate(users)}
    auth = CompanionAuth(storage, lambda uid: state[uid], profiles=profiles)
    return auth, profiles, state


def enroll_user(auth, uid, identity=IDENTITY):
    key, public = key_pair()
    ticket = auth.issue_ticket('123456', ORIGIN, profile_id=uid)
    claim = auth.claim(ticket, ORIGIN, identity, public,
                       sign(key, enrollment_message(ticket, ORIGIN, identity, public)))
    auth.approve('123456', claim['device_id'], claim['comparison_code'])
    return key, claim['device_id']


def proof(auth, key, device, identity=IDENTITY):
    nonce = auth.challenge(device, ORIGIN, identity, 'GET', PATH, hashlib.sha256(b'').hexdigest())['nonce']
    return device, nonce, ORIGIN, identity, 'GET', PATH, b'', sign(key, request_message(device, nonce, ORIGIN, identity, 'GET', PATH, b''))


def test_all_five_sessions_derive_role_from_registry_not_presence_or_caller(rig):
    auth, profiles, state = rig
    devices = {}
    for user in profiles.list():
        # Even a facade with a forged primary role cannot promote a guest.
        state[user.id] = replace(state[user.id], profile_id=PRIMARY_ID, role='primary')
        key, device = enroll_user(auth, user.id)
        initial = auth.verify(*proof(auth, key, device))
        assert initial.profile_id == user.id and initial.role == user.role
        devices[device] = user.id
    saved = json.loads(profiles.storage.get_secret(GRANTS_KEY))
    assert {device: row['profile_id'] for device, row in saved.items()} == devices
    legacy = json.loads(profiles.storage.get_secret(LEGACY_KEY))
    assert list(legacy) == [device for device, uid in devices.items() if uid == PRIMARY_ID]
    assert all('profile_id' not in row for row in legacy.values())


@pytest.mark.parametrize('change', ['disconnect', 'generation', 'binding', 'removed', 'disabled', 'policy'])
def test_guest_authority_revokes_without_interrupting_primary_or_other_guest(rig, change):
    auth, profiles, state = rig
    primary, first, other = profiles.list()[:3]
    primary_key, primary_device = enroll_user(auth, primary.id)
    other_key, other_device = enroll_user(auth, other.id)
    key, device = enroll_user(auth, first.id)
    initial = auth.verify(*proof(auth, key, device))
    old = proof(auth, key, device)
    primary_proof = proof(auth, primary_key, primary_device)
    other_proof = proof(auth, other_key, other_device)
    if change == 'disconnect': state[first.id] = replace(state[first.id], authorized=False)
    elif change == 'generation': state[first.id] = replace(state[first.id], generation='new-session')
    elif change == 'binding': profiles.bind_phone(first.id, '11:22:33:44:55:66')
    elif change == 'removed': profiles.remove(first.id)
    elif change == 'disabled': profiles.set_remote_enabled(first.id, False)
    else: profiles.set_remote_policy('primary_only')
    with pytest.raises(CompanionDenied): auth.verify(*old)
    with pytest.raises(CompanionDenied): auth.still_authorized(device, ORIGIN, IDENTITY, initial)
    assert auth.verify(*primary_proof).profile_id == PRIMARY_ID
    if change != 'policy':
        assert auth.verify(*other_proof).profile_id == other.id
    else:
        with pytest.raises(CompanionDenied): auth.verify(*other_proof)
        profiles.set_remote_policy('all_profiles')
        with pytest.raises(CompanionDenied): auth.verify(*proof(auth, key, device))


def test_primary_absence_does_not_prevent_approved_guest_from_using_own_browser(rig):
    auth, profiles, state = rig
    guest = profiles.list()[1]
    key, device = enroll_user(auth, guest.id)
    state[PRIMARY_ID] = replace(state[PRIMARY_ID], authorized=False)
    assert auth.verify(*proof(auth, key, device)).profile_id == guest.id


@pytest.mark.parametrize('change', ['disconnect', 'generation', 'binding', 'removed', 'disabled', 'policy'])
def test_guest_enrollment_cannot_survive_binding_presence_or_policy_change(rig, change):
    auth, profiles, state = rig
    uid = profiles.list()[1].id
    key, public = key_pair()
    ticket = auth.issue_ticket('123456', ORIGIN, profile_id=uid)
    claim = auth.claim(ticket, ORIGIN, IDENTITY, public, sign(key, enrollment_message(ticket, ORIGIN, IDENTITY, public)))
    if change == 'disconnect': state[uid] = replace(state[uid], authorized=False)
    elif change == 'generation': state[uid] = replace(state[uid], generation='replacement')
    elif change == 'binding': profiles.bind_phone(uid, '11:22:33:44:55:66')
    elif change == 'removed': profiles.remove(uid)
    elif change == 'disabled': profiles.set_remote_enabled(uid, False)
    else: profiles.set_remote_policy('primary_only')
    with pytest.raises(CompanionDenied): auth.approve('123456', claim['device_id'], claim['comparison_code'])
    assert claim['device_id'] not in json.loads(profiles.storage.get_secret(GRANTS_KEY) or '{}')


def test_legacy_primary_grants_migrate_once_without_requiring_primary_presence(rig):
    auth, profiles, state = rig
    storage = profiles.storage
    legacy = CompanionAuth(storage, lambda: state[PRIMARY_ID])
    key, device = enroll(legacy)
    original = storage.get_secret(LEGACY_KEY)
    state[PRIMARY_ID] = replace(state[PRIMARY_ID], authorized=False)
    assert auth.devices('123456') == [{'device_id': device, 'label': 'iPhone browser', 'profile_id': PRIMARY_ID}]
    assert storage.get_secret(LEGACY_KEY) == original
    state[PRIMARY_ID] = replace(state[PRIMARY_ID], authorized=True)
    assert auth.verify(*proof(auth, key, device)).profile_id == PRIMARY_ID
    auth.revoke('123456', device)
    assert json.loads(storage.get_secret(LEGACY_KEY)) == {}
    # Stale rollback state or a restored backup cannot silently remigrate.
    storage.set_secret(LEGACY_KEY, original)
    with storage.transaction() as db:
        db.execute('DELETE FROM secrets WHERE key=?', (GRANTS_KEY,))
    restarted = CompanionAuth(storage, lambda uid: state[uid], profiles=profiles)
    assert restarted.devices('123456') == []
    with pytest.raises(CompanionDenied): restarted.challenge(device, ORIGIN, IDENTITY, 'GET', PATH, hashlib.sha256(b'').hexdigest())


def test_revocation_by_another_auth_instance_cannot_be_overwritten_by_approval(rig):
    auth, profiles, state = rig
    key, device = enroll_user(auth, PRIMARY_ID)
    second = CompanionAuth(profiles.storage, lambda uid: state[uid], profiles=profiles)
    second.revoke('123456', device)
    enroll_user(auth, profiles.list()[1].id)
    assert device not in json.loads(profiles.storage.get_secret(GRANTS_KEY))
    with pytest.raises(CompanionDenied): auth.verify(*proof(auth, key, device))


def test_ticket_target_is_not_selected_by_claimant_identity(rig):
    auth, profiles, _ = rig
    guest = profiles.list()[1]
    key, device = enroll_user(auth, guest.id, identity='guest@example.test')
    assert auth.verify(*proof(auth, key, device, identity='guest@example.test')).profile_id == guest.id
    with pytest.raises(CompanionDenied): proof(auth, key, device, identity=IDENTITY)


def test_corrupt_migration_does_not_erase_records_or_crash_local_application_construction(rig):
    auth, profiles, state = rig
    profiles.storage.set_secret(LEGACY_KEY, 'corrupt')
    restarted = CompanionAuth(profiles.storage, lambda uid: state[uid], profiles=profiles)
    with pytest.raises(CompanionDenied): restarted.devices('123456')
    assert profiles.storage.get_secret(LEGACY_KEY) == 'corrupt'
    assert profiles.storage.get_secret(GRANTS_KEY) is None
