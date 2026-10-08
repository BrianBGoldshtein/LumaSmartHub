from datetime import UTC, datetime, timedelta
from itertools import product
from types import SimpleNamespace
from unittest.mock import Mock
import json

import pytest
from google.auth.exceptions import RefreshError

from luma.integrations.google_calendar import TOKEN_KEY, TaskConflict
from luma.models import CalendarEvent
from luma.profile_calendars import ProfileCalendars
from luma.profiles import ProfileRepository, ProfileError
from luma.storage import Storage

NOW = datetime(2026, 10, 8, 18, tzinfo=UTC)


@pytest.fixture
def accounts(tmp_path):
    profiles = ProfileRepository(Storage(tmp_path/'luma.db'))
    users = [profiles.get('primary')] + [profiles.create_secondary(f'Guest {i}') for i in range(4)]
    present = set()
    for index, user in enumerate(users):
        profiles.bind_phone(user.id, f'AA:BB:CC:DD:EE:{index+1:02X}')
        profiles.set_setup(user.id, 'ready', wall_share_approved=True)
        profiles.update_personal(user.id, {'visible_calendar_ids': ['same-calendar'], 'todo_calendar_id': 'tasks', 'todo_completed_color_id': '5'})
    def presence(uid):
        return SimpleNamespace(authorized=uid in present, address=profiles.get(uid).phone_address, generation='session-'+uid)
    manager = ProfileCalendars(profiles, presence, clock=lambda: NOW)
    for user in users:
        account = manager.account(user.id)
        account.google.authorized = Mock(return_value=True)
        account.google.task_write_authorized = Mock(return_value=True)
        account.events = [CalendarEvent('same-id', 'same-calendar', user.id+' event', NOW, NOW+timedelta(hours=1))]
    return manager, users, present


@pytest.mark.parametrize('combination', list(product([False, True], repeat=5)))
def test_every_presence_combination_filters_each_profile_without_pin_or_grace(accounts, combination):
    manager, users, present = accounts
    present.update(user.id for user, active in zip(users, combination) if active)
    panels = manager.wall_panels()
    assert {row['profile_id'] for row in panels} == present
    for row in panels:
        assert row['calendar'][0]['summary'] == row['profile_id']+' event'
        assert row['calendar'][0]['profile_id'] == row['profile_id']
    for user in users:
        assert (manager.projection(user.id) is not None) == (user.id in present)


def test_secondary_can_preview_own_before_wall_sharing_but_not_other_data(accounts):
    manager, users, present = accounts
    guest = users[1]
    manager.profiles.set_setup(guest.id, 'calendars', wall_share_approved=False)
    present.add(guest.id)
    assert manager.wall_panels() == []
    assert manager.projection(guest.id)['calendar'][0]['summary'] == guest.id+' event'
    assert manager.projection('primary') is None


@pytest.mark.asyncio
async def test_sync_accounts_independently_and_invalid_grant_does_not_mask_other_accounts(accounts):
    manager, users, present = accounts
    for user in users:
        account = manager.account(user.id)
        account.google.fetch_events = Mock(return_value=account.events)
    bad = manager.account(users[2].id)
    bad.google.fetch_events.side_effect = RefreshError('rejected', {'error': 'invalid_grant'})
    for user in users:
        if user == users[2]:
            with pytest.raises(RefreshError): await manager.sync(user.id)
        else:
            assert (await manager.sync(user.id))['count'] == 1
    assert bad.status['reconnect_required']
    assert bad.events[0].summary == users[2].id+' event'
    for user in users:
        if user != users[2]:
            assert manager.fresh(user.id)
            assert not manager.account(user.id).status['error']
            assert manager.profiles.account_storage(user.id).get_cache('calendar', 'events')[0]['summary'] == user.id+' event'


@pytest.mark.asyncio
async def test_no_calendar_selection_clears_only_own_cache_and_updates_freshness(accounts):
    manager, users, _ = accounts
    uid = users[1].id
    manager.profiles.update_personal(uid, {'visible_calendar_ids': [], 'todo_calendar_id': None})
    assert await manager.sync(uid) == {'count': 0}
    assert manager.fresh(uid)
    assert manager.account(uid).events == []
    assert manager.account('primary').events


@pytest.mark.asyncio
async def test_selection_change_while_provider_runs_does_not_install_wrong_account_data(accounts):
    manager, users, _ = accounts
    uid = users[1].id
    before = list(manager.account(uid).events)
    def fetch(*args):
        manager.profiles.update_personal(uid, {'visible_calendar_ids': ['changed']})
        return []
    manager.account(uid).google.fetch_events = fetch
    with pytest.raises(ProfileError): await manager.sync(uid)
    assert manager.account(uid).events == before


@pytest.mark.asyncio
async def test_removed_account_cannot_be_restored_by_inflight_sync(accounts):
    manager, users, _ = accounts
    uid = users[1].id
    account = manager.account(uid)
    def fetch(*args): manager.profiles.remove(uid); return []
    account.google.fetch_events = fetch
    with pytest.raises(ProfileError): await manager.sync(uid)
    with manager.profiles.storage.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM cache WHERE namespace LIKE ?', (f'profile:{uid}:%',)).fetchone()[0] == 0


def task(uid, completed=False):
    return CalendarEvent('same-task', 'tasks', uid+' task', NOW.replace(hour=0), NOW.replace(hour=0)+timedelta(days=2),
        all_day=True, etag='revision', calendar_writable=True, event_color_id='5' if completed else None)


@pytest.mark.asyncio
async def test_identical_task_ids_use_only_authenticated_account_client(accounts):
    manager, users, present = accounts
    present.update(user.id for user in users)
    for user in users:
        account = manager.account(user.id)
        account.events.append(task(user.id))
        account.google.recolor_task = Mock(return_value=task(user.id, True))
    uid = users[1].id
    result = await manager.complete_task(uid, calendar_id='tasks', event_id='same-task', etag='revision', completed=True)
    assert result['todos'][0]['completed']
    assert result['todos'][0]['summary'] == uid+' task'
    manager.account(uid).google.recolor_task.assert_called_once()
    for user in users:
        if user.id != uid: manager.account(user.id).google.recolor_task.assert_not_called()


@pytest.mark.asyncio
async def test_task_disconnect_and_revision_conflict_do_not_send_provider_write(accounts):
    manager, users, present = accounts
    uid = users[1].id
    account = manager.account(uid)
    account.events.append(task(uid))
    account.google.recolor_task = Mock()
    with pytest.raises(PermissionError):
        await manager.complete_task(uid, calendar_id='tasks', event_id='same-task', etag='revision', completed=True)
    present.add(uid)
    with pytest.raises(TaskConflict):
        await manager.complete_task(uid, calendar_id='tasks', event_id='same-task', etag='old', completed=True)
    account.google.recolor_task.assert_not_called()


@pytest.mark.asyncio
async def test_task_provider_response_withheld_after_disconnect(accounts):
    manager, users, present = accounts
    uid = users[1].id
    present.add(uid)
    account = manager.account(uid)
    account.events.append(task(uid))
    def recolor(**kwargs): present.clear(); return task(uid, True)
    account.google.recolor_task = recolor
    with pytest.raises(PermissionError):
        await manager.complete_task(uid, calendar_id='tasks', event_id='same-task', etag='revision', completed=True)
    assert account.events[-1].event_color_id is None


def test_secondary_settings_cannot_inherit_primary_room_sleep_calendars(accounts):
    manager, users, _ = accounts
    settings = manager.profiles.storage.load_settings()
    settings.sleep_calendar_ids = ['primary-sleep']
    manager.profiles.storage.save_settings(settings)
    assert manager.settings('primary').sleep_calendar_ids == ['primary-sleep']
    assert manager.settings(users[1].id).sleep_calendar_ids == []
