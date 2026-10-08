from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json
from unittest.mock import Mock

import pytest

from luma.focus_timer import FocusTimer
from luma.integrations.google_calendar import GoogleCalendarClient, TOKEN_KEY, OAUTH_STATE_KEY
from luma.personal_timers import PersonalTimers
from luma.profiles import ProfileRepository, ProfileError, REGISTRY_KEY, GRANTS_KEY, PERSONAL_KEYS, REMOTE_POLICY_KEY
from luma.storage import Storage


@pytest.fixture
def profiles(tmp_path):
    return ProfileRepository(Storage(tmp_path/'luma.db'))


def test_migration_preserves_primary_legacy_records_and_reads_rollback_edits(profiles):
    store = profiles.storage
    saved = store.load_settings()
    saved.phone_address = 'AA:BB:CC:DD:EE:01'
    saved.visible_calendar_ids = ['brian-calendar']
    saved.todo_calendar_id = 'tasks'
    store.save_settings(saved)
    store.set_secret(TOKEN_KEY, 'primary-grant')
    store.set_cache('games', 'blocks', {'score': 22000})
    assert profiles.get('primary').phone_address == saved.phone_address
    assert profiles.get('primary').personal['visible_calendar_ids'] == ['brian-calendar']
    assert GoogleCalendarClient(profiles.account_storage('primary')).authorized()
    assert profiles.account_storage('primary').get_secret(TOKEN_KEY) == 'primary-grant'
    saved.visible_calendar_ids = ['changed-on-old-version']
    store.save_settings(saved)
    assert profiles.get('primary').personal['visible_calendar_ids'] == saved.visible_calendar_ids
    assert store.get_cache('games', 'blocks') == {'score': 22000}
    assert store.integrity_check()


def test_capacity_is_atomic_across_repositories(profiles):
    def add(number):
        try:
            return ProfileRepository(Storage(profiles.storage.path)).create_secondary(f'Guest {number}').id
        except ProfileError:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(add, range(12)))
    assert len([uid for uid in results if uid]) == 4
    assert len(profiles.list()) == 5
    with pytest.raises(ProfileError, match='up to four'):
        profiles.create_secondary('Extra')


@pytest.mark.parametrize('name', ['', ' '*8, 'a'*25, 'Brian\n', '\u202eBrian', 42])
def test_bad_nickname_rejected_without_mutation(profiles, name):
    before = profiles.list()
    with pytest.raises(ProfileError):
        profiles.create_secondary(name)
    assert profiles.list() == before


def test_names_are_normalized_and_unambiguous(profiles):
    profiles.rename('primary', ' Brian ')
    with pytest.raises(ProfileError):
        profiles.create_secondary('bRIAN')
    user = profiles.create_secondary('Cafe\u0301')
    assert user.nickname == 'Café'
    with pytest.raises(ProfileError):
        profiles.create_secondary('Café')


def test_duplicate_phones_rejected_in_profile_and_legacy_routes(profiles):
    user = profiles.create_secondary('Alex')
    profiles.bind_phone(user.id, 'aa:bb:cc:dd:ee:01')
    assert profiles.by_phone('AA:BB:CC:DD:EE:01').id == user.id
    assert profiles.by_phone(None) is None
    with pytest.raises(ProfileError):
        profiles.bind_phone('primary', 'AA:BB:CC:DD:EE:01')
    saved = profiles.storage.load_settings()
    saved.phone_address = 'AA:BB:CC:DD:EE:01'
    with pytest.raises(ProfileError):
        profiles.storage.save_settings(saved)
    assert profiles.storage.load_settings().phone_address is None


def test_primary_personal_changes_remain_canonical_and_room_settings_untouched(profiles):
    profiles.update_personal('primary', {'visible_calendar_ids': ['new'], 'departure_enabled': True})
    assert profiles.storage.load_settings().visible_calendar_ids == ['new']
    before = profiles.storage.load_settings()
    with pytest.raises(ProfileError):
        profiles.update_personal('primary', {'brightness': 3})
    assert profiles.storage.load_settings() == before


@pytest.mark.parametrize('updates', [
    {'visible_calendar_ids': ['a', 'a']}, {'visible_calendar_ids': [None]},
    {'todo_calendar_id': ''}, {'visible_calendar_ids': ['a']*51},
    {'departure_enabled': 1}, {'departure_prep_minutes': True},
    {'todo_completed_color_id': '0'}, {'sleep_calendar_ids': ['room']}, {'role': 'primary'},
])
def test_secondary_personal_validation(profiles, updates):
    user = profiles.create_secondary('Alex')
    with pytest.raises(ProfileError):
        profiles.update_personal(user.id, updates)
    assert profiles.get(user.id) == user


def test_scoped_account_secrets_cache_and_consumption_are_isolated(profiles):
    one, two = [profiles.create_secondary(name) for name in ('Alex', 'Sam')]
    first, second = [profiles.account_storage(user.id) for user in (one, two)]
    first.set_secret(TOKEN_KEY, 'alex-token')
    second.set_secret(TOKEN_KEY, 'sam-token')
    first.set_secret(OAUTH_STATE_KEY, 'alex-pending')
    second.set_secret(OAUTH_STATE_KEY, 'sam-pending')
    first.set_cache('calendar', 'events', [{'id': 'same-id', 'summary': 'Alex'}])
    second.set_cache('calendar', 'events', [{'id': 'same-id', 'summary': 'Sam'}])
    assert profiles.storage.get_secret(TOKEN_KEY) is None
    assert first.get_cache('calendar', 'events')[0]['summary'] == 'Alex'
    assert second.get_cache('calendar', 'events')[0]['summary'] == 'Sam'
    assert not first.consume_secret(OAUTH_STATE_KEY, 'sam-pending')
    assert first.consume_secret(OAUTH_STATE_KEY, 'alex-pending')
    assert not first.consume_secret(OAUTH_STATE_KEY, 'alex-pending')
    assert second.get_secret(OAUTH_STATE_KEY) == 'sam-pending'
    assert GoogleCalendarClient(first).authorized()
    assert GoogleCalendarClient(second).authorized()


def test_phone_change_revokes_only_affected_profile(profiles):
    user = profiles.create_secondary('Alex')
    profiles.storage.set_secret(GRANTS_KEY, json.dumps({'one': {'profile_id': user.id}, 'two': {'profile_id': 'primary'}}))
    profiles.storage.set_secret('companion_browser_grants_v1', 'legacy-grant')
    profiles.bind_phone(user.id, 'AA:BB:CC:DD:EE:01')
    assert json.loads(profiles.storage.get_secret(GRANTS_KEY)) == {'two': {'profile_id': 'primary'}}
    assert profiles.storage.get_secret('companion_browser_grants_v1') == 'legacy-grant'
    settings = profiles.storage.load_settings()
    settings.phone_address = 'AA:BB:CC:DD:EE:02'
    profiles.storage.save_settings(settings)
    assert json.loads(profiles.storage.get_secret(GRANTS_KEY)) == {}
    assert profiles.storage.get_secret('companion_browser_grants_v1') is None


def test_removal_cannot_resurrect_credentials_and_preserves_others(profiles):
    one, two = [profiles.create_secondary(name) for name in ('Alex', 'Sam')]
    scoped = profiles.account_storage(one.id)
    scoped.set_secret(TOKEN_KEY, 'alex')
    scoped.set_cache('calendar', 'events', [])
    profiles.account_storage(two.id).set_secret(TOKEN_KEY, 'sam')
    profiles.remove(one.id)
    for action in (lambda: scoped.get_secret(TOKEN_KEY), lambda: scoped.set_secret(TOKEN_KEY, 'late-refresh'),
                   lambda: scoped.set_cache('calendar', 'events', [])):
        with pytest.raises(ProfileError):
            action()
    assert profiles.account_storage(two.id).get_secret(TOKEN_KEY) == 'sam'
    with pytest.raises(ProfileError):
        profiles.remove('primary')
    with profiles.storage.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM secrets WHERE key LIKE ?', (f'profile:{one.id}:%',)).fetchone()[0] == 0


def test_backup_restore_keeps_profiles_google_but_not_grants_or_pending_consent(profiles, tmp_path):
    user = profiles.create_secondary('Alex')
    scoped = profiles.account_storage(user.id)
    scoped.set_secret(TOKEN_KEY, 'alex')
    scoped.set_secret(OAUTH_STATE_KEY, 'pending')
    profiles.storage.set_secret(GRANTS_KEY, '{}')
    backup = profiles.storage.backup(tmp_path/'backup.db')
    restored = Storage(tmp_path/'restored.db')
    restored.restore(backup)
    repository = ProfileRepository(restored)
    assert repository.get(user.id) == user
    assert repository.account_storage(user.id).get_secret(TOKEN_KEY) == 'alex'
    assert repository.account_storage(user.id).get_secret(OAUTH_STATE_KEY) is None
    assert restored.get_secret(GRANTS_KEY) is None
    assert restored.integrity_check()


def test_corrupt_registry_is_not_silently_reset(profiles):
    with profiles.storage.transaction() as connection:
        connection.execute('UPDATE metadata SET value=? WHERE key=?', ('{"version":true,"users":[]}', REGISTRY_KEY))
    with pytest.raises(ProfileError, match='no accounts were reset'):
        ProfileRepository(profiles.storage)
    with profiles.storage.connect() as connection:
        assert connection.execute('SELECT value FROM metadata WHERE key=?', (REGISTRY_KEY,)).fetchone()[0] == '{"version":true,"users":[]}'


def test_setup_can_skip_google_and_remote_can_be_explicitly_disabled(profiles):
    user = profiles.create_secondary('Alex')
    profiles.set_remote_enabled(user.id, False)
    profiles.set_setup(user.id, 'ready', wall_share_approved=True)
    assert not profiles.get(user.id).remote_enabled
    assert profiles.get(user.id).wall_share_approved
    assert profiles.get(user.id).personal['visible_calendar_ids'] == []
    with pytest.raises(ProfileError):
        profiles.set_remote_enabled('primary', False)


def test_primary_only_remote_fallback_keeps_profiles_wall_and_account_state(profiles):
    users = [profiles.create_secondary(name) for name in ('Alex', 'Sam', 'Pat', 'Robin')]
    for number, user in enumerate(users):
        profiles.bind_phone(user.id, f'AA:BB:CC:DD:EE:{number+1:02X}')
        profiles.set_setup(user.id, 'ready', wall_share_approved=True)
        profiles.account_storage(user.id).set_secret(TOKEN_KEY, f'google-{number}')
        profiles.account_storage(user.id).set_cache('personal_timer', 'active', {'label': f'timer-{number}'})
    profiles.storage.set_secret('companion_browser_grants_v1', 'legacy-primary')
    profiles.storage.set_secret(GRANTS_KEY, json.dumps({
        'primary': {'profile_id': 'primary'},
        **{user.id: {'profile_id': user.id} for user in users},
    }))
    before = profiles.list()
    assert profiles.remote_policy() == 'all_profiles'
    assert all(profiles.remote_allowed(user.id) for user in before)
    profiles.set_remote_policy('primary_only')
    assert profiles.remote_allowed('primary')
    assert not any(profiles.remote_allowed(user.id) for user in users)
    assert profiles.list() == before
    assert json.loads(profiles.storage.get_secret(GRANTS_KEY)) == {'primary': {'profile_id': 'primary'}}
    assert profiles.storage.get_secret('companion_browser_grants_v1') == 'legacy-primary'
    for number, user in enumerate(users):
        store = profiles.account_storage(user.id)
        assert store.get_secret(TOKEN_KEY) == f'google-{number}'
        assert store.get_cache('personal_timer', 'active') == {'label': f'timer-{number}'}
    profiles.set_remote_policy('all_profiles')
    assert all(profiles.remote_allowed(user.id) for user in users)
    assert json.loads(profiles.storage.get_secret(GRANTS_KEY)) == {'primary': {'profile_id': 'primary'}}


def test_global_remote_policy_does_not_override_individual_disable(profiles):
    user = profiles.create_secondary('Alex')
    profiles.set_remote_enabled(user.id, False)
    profiles.set_remote_policy('primary_only')
    profiles.set_remote_policy('all_profiles')
    assert not profiles.remote_allowed(user.id)
    with pytest.raises(ProfileError):
        profiles.remote_allowed('removed-user')


@pytest.mark.parametrize('policy', ['public', '', None, True, {}, []])
def test_remote_policy_rejects_unknown_modes_without_mutation(profiles, policy):
    before = profiles.list()
    with pytest.raises(ProfileError):
        profiles.set_remote_policy(policy)
    assert profiles.remote_policy() == 'all_profiles'
    assert profiles.list() == before


def test_corrupt_remote_policy_fails_closed_without_reset(profiles):
    user = profiles.create_secondary('Alex')
    with profiles.storage.transaction() as connection:
        connection.execute('INSERT INTO metadata(key,value) VALUES(?,?)', (REMOTE_POLICY_KEY, 'public'))
    for uid in ('primary', user.id):
        with pytest.raises(ProfileError, match='policy needs local recovery'):
            profiles.remote_allowed(uid)
    assert profiles.get(user.id) == user


def test_remote_policy_survives_restart_and_backup_restore(profiles, tmp_path):
    user = profiles.create_secondary('Alex')
    profiles.set_remote_policy('primary_only')
    restarted = ProfileRepository(Storage(profiles.storage.path))
    assert not restarted.remote_allowed(user.id)
    backup = profiles.storage.backup(tmp_path/'remote-policy-backup.db')
    restored = Storage(tmp_path/'remote-policy-restored.db')
    restored.restore(backup)
    repository = ProfileRepository(restored)
    assert repository.remote_policy() == 'primary_only'
    assert repository.remote_allowed('primary')
    assert not repository.remote_allowed(user.id)


def test_personal_timers_do_not_replace_room_or_each_other_and_recover(profiles):
    now = datetime(2026, 10, 8, 18, tzinfo=UTC)
    clock = Mock(return_value=100.)
    one, two = [profiles.create_secondary(name) for name in ('Alex', 'Sam')]
    room = FocusTimer(profiles.storage, clock=clock)
    bank = PersonalTimers(profiles, clock=clock)
    room.tick(now, trusted=True)
    bank.tick(now, trusted=True)
    room.execute('start_timer', {'seconds': 60, 'label': 'Room'}, now=now)
    for uid, seconds in (('primary', 120), (one.id, 180), (two.id, 240)):
        assert bank.for_user(uid).execute('start_timer', {'seconds': seconds, 'label': 'Private label'}, now=now).accepted
    assert room.snapshot()['duration_seconds'] == 60
    assert [bank.for_user(uid).snapshot()['duration_seconds'] for uid in ('primary', one.id, two.id)] == [120, 180, 240]
    recovered = PersonalTimers(profiles, clock=clock)
    recovered.tick(now+timedelta(seconds=30), trusted=True)
    assert recovered.for_user(one.id).snapshot()['remaining_seconds'] == 150
    view = {row['profile_id']: row for row in recovered.snapshot({one.id})}
    assert view[one.id]['label'] == 'Private label'
    assert view[two.id]['label'] == 'Timer'
    assert room.snapshot()['label'] == 'Room'


def test_personal_completions_coalesce_even_absent_or_muted(profiles):
    now = datetime(2026, 10, 8, 18, tzinfo=UTC)
    clock = Mock(return_value=100.)
    user = profiles.create_secondary('Alex')
    bank = PersonalTimers(profiles, clock=clock)
    bank.tick(now, trusted=True)
    for uid in ('primary', user.id):
        bank.for_user(uid).execute('start_timer', {'seconds': 1}, now=now)
    clock.return_value = 101.
    assert bank.tick(now+timedelta(seconds=1))
    assert bank.claim_chime()
    assert not bank.claim_chime()
    for uid in ('primary', user.id):
        bank.for_user(uid).execute('start_timer', {'seconds': 1}, now=now)
    clock.return_value = 102.
    bank.tick(now+timedelta(seconds=2))
    assert not bank.claim_chime(muted=True)
    assert not bank.claim_chime()
