"""Per-account Google sync and private projections; no shared token/event list."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Callable

from .agenda import day_agenda
from .calendar_logic import ongoing_events, todo_events, todo_view, visible_events
from .departures import Departures
from .integrations.google_calendar import GoogleCalendarClient, calendar_failure_status, TaskConflict
from .profiles import PRIMARY_ID, ProfileError, ProfileRepository
from .serde import calendar_event_from_dict, to_primitive


@dataclass
class CalendarAccount:
    storage: object
    google: GoogleCalendarClient
    departures: Departures
    events: list
    status: dict
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def utc_now():
    return datetime.now(UTC)


class ProfileCalendars:
    def __init__(self, profiles: ProfileRepository, presence: Callable[[str], object],
                 *, clock=utc_now, publish=lambda *args: None, primary_changed=None):
        self.profiles, self.presence, self.clock = profiles, presence, clock
        self.publish, self.primary_changed = publish, primary_changed
        self.accounts: dict[str, CalendarAccount] = {}
        self.provider_slots = asyncio.Semaphore(2)

    def account(self, uid: str) -> CalendarAccount:
        self.profiles.get(uid)
        if uid not in self.accounts:
            store = self.profiles.account_storage(uid)
            google = GoogleCalendarClient(store)
            raw = store.get_cache('calendar', 'events') or []
            try:
                if not isinstance(raw, list) or len(raw) > 10000:
                    raise ValueError
                events = [calendar_event_from_dict(item) for item in raw]
            except (ValueError, TypeError, KeyError):
                events = []  # A malformed guest cache cannot crash other users.
            status = {'last_synced': None, 'error': None, 'error_kind': None, 'reconnect_required': False}
            saved = store.get_cache('calendar', 'sync_status')
            if isinstance(saved, dict) and isinstance(saved.get('last_synced'), str):
                try:
                    date = datetime.fromisoformat(saved['last_synced'])
                    if date.tzinfo is not None:
                        status['last_synced'] = date.astimezone(UTC).isoformat()
                except ValueError:
                    pass
            self.accounts[uid] = CalendarAccount(store, google, Departures(store), events, status)
        return self.accounts[uid]

    def settings(self, uid: str):
        user = self.profiles.get(uid)
        room = self.profiles.storage.load_settings()
        return replace(room, **user.personal,
                       sleep_calendar_ids=room.sleep_calendar_ids if user.primary else [])

    def present(self, uid: str) -> bool:
        try:
            phone = self.presence(uid)
            user = self.profiles.get(uid)
            return bool(phone.authorized and phone.address == user.phone_address and phone.generation)
        except Exception:
            return False

    def _require_present(self, uid):
        if not self.present(uid):
            raise PermissionError('Connect this user’s authorized phone first.')

    def fresh(self, uid: str, now=None):
        status = self.account(uid).status
        try:
            age = (now or self.clock()) - datetime.fromisoformat(status['last_synced'])
            return not status['error'] and timedelta(0) <= age <= timedelta(minutes=10)
        except (ValueError, TypeError):
            return False

    async def sync(self, uid: str, *, recheck=lambda: None):
        account = self.account(uid)
        async with account.lock:
            recheck()
            settings = self.settings(uid)
            if not account.google.authorized():
                raise PermissionError('Connect this user’s Google account first.')
            ids = list(dict.fromkeys(settings.visible_calendar_ids + settings.sleep_calendar_ids +
                (settings.departure_calendar_ids if settings.departure_enabled else []) +
                ([settings.todo_calendar_id] if settings.todo_calendar_id else [])))
            started = self.clock()
            try:
                async with self.provider_slots:
                    recheck()
                    events = await asyncio.to_thread(account.google.fetch_events, ids,
                        started-timedelta(days=7), started+timedelta(days=7), settings.timezone) if ids else []
                recheck()
                # Don't commit an old selection after setup/remove changes.
                if self.settings(uid) != settings:
                    raise ProfileError('Calendar selections changed. Sync this user again.')
                account.storage.set_cache('calendar', 'events', events)
                account.storage.set_cache('calendar', 'sync_status', {'last_synced': started.isoformat()})
            except Exception as error:
                if not account.status['reconnect_required']:
                    account.status.update(calendar_failure_status(error))
                self.publish('user.calendar.stale', {'profile_id': uid})
                raise
            account.events = events
            account.status.update(last_synced=started.isoformat(), error=None, error_kind=None, reconnect_required=False)
            if uid == PRIMARY_ID and self.primary_changed:
                self.primary_changed(events, started)
            self.publish('user.calendar.updated', {'profile_id': uid})
            return {'count': len(events)}

    def projection(self, uid: str, *, wall=False, now=None):
        user = self.profiles.get(uid)
        if not self.present(uid) or (wall and not user.wall_share_approved):
            return None
        account, settings, now = self.account(uid), self.settings(uid), now or self.clock()
        current = visible_events(account.events, now=now, calendar_ids=set(settings.visible_calendar_ids),
                                 sleep_calendar_ids=set(settings.sleep_calendar_ids), sleep_title=settings.sleep_event_title)
        tasks = todo_events(account.events, todo_calendar_id=settings.todo_calendar_id, now=now)
        tag = lambda rows: [{**row, 'profile_id': uid} for row in to_primitive(rows)]
        agenda = day_agenda(account.events, settings, now, fresh=self.fresh(uid, now))
        agenda['events'] = tag(agenda['events'])
        tasks_view = sorted((todo_view(event, settings.todo_completed_color_id) for event in tasks),
                            key=lambda row: (row['completed'], row['due_date'], row['summary'].casefold(), row['id']))
        result = {'profile_id': uid, 'nickname': user.nickname,
            'calendar': tag(current), 'ongoing': tag(ongoing_events(current, now)), 'agenda': agenda,
            'todos': tag(tasks_view), 'configured': bool(settings.visible_calendar_ids or settings.todo_calendar_id),
            'todo_controls': {'can_update': bool(account.google.task_write_authorized() and
                settings.todo_calendar_id and settings.todo_completed_color_id and any(event.calendar_writable for event in tasks)),
                'stale': not self.fresh(uid, now)},
            'google': {'authorized': account.google.authorized(), **account.status},
            'departure': account.departures.snapshot(account.events, settings, now, fresh=self.fresh(uid, now))}
        # Revocation/removal or disconnect wins over a slow projection build.
        return result if self.present(uid) and (not wall or self.profiles.get(uid).wall_share_approved) else None

    def wall_panels(self, now=None):
        now = now or self.clock()
        return [view for user in self.profiles.list() if (view := self.projection(user.id, wall=True, now=now)) is not None]

    async def complete_task(self, uid: str, *, calendar_id: str, event_id: str, etag: str,
                            completed: bool, recheck=lambda: None):
        account = self.account(uid)
        async with account.lock:
            recheck()
            self._require_present(uid)
            settings = self.settings(uid)
            if (type(completed) is not bool or calendar_id != settings.todo_calendar_id or
                    not settings.todo_completed_color_id):
                raise ValueError('Choose this user’s task calendar and completed color first.')
            current = next((event for event in todo_events(account.events, todo_calendar_id=settings.todo_calendar_id,
                           now=self.clock()) if event.id == event_id), None)
            if current is None or current.etag != etag:
                raise TaskConflict('This task changed. Refresh your calendar before trying again.')
            async with self.provider_slots:
                recheck()
                self._require_present(uid)
                updated = await asyncio.to_thread(account.google.recolor_task, calendar_id=calendar_id,
                    event_id=current.id, expected_etag=etag, color_id=settings.todo_completed_color_id if completed else None,
                    timezone=settings.timezone, now=self.clock())
            recheck()
            self._require_present(uid)
            if self.settings(uid) != settings:
                raise ProfileError('Calendar selections changed. Refresh before retrying.')
            updated.calendar_name, updated.calendar_color = current.calendar_name, current.calendar_color
            updated.calendar_writable = current.calendar_writable
            events = [updated if event.calendar_id == calendar_id and event.id == event_id else event for event in account.events]
            account.storage.set_cache('calendar', 'events', events)
            account.events = events
            if uid == PRIMARY_ID and self.primary_changed:
                self.primary_changed(events, self.clock())
            self.publish('user.calendar.updated', {'profile_id': uid})
            return self.projection(uid)

    async def worker(self, *, pause=asyncio.sleep):
        while True:
            users = self.profiles.list()
            live = {user.id for user in users}
            self.accounts = {uid: account for uid, account in self.accounts.items() if uid in live}
            for index, user in enumerate(users):
                if index:
                    await pause(5)  # Avoid five simultaneous credential refreshes on Pi 4.
                try:
                    if self.account(user.id).google.authorized():
                        await self.sync(user.id)
                except Exception:
                    pass  # Per-account status records the fixed failure.
            await pause(max(1, 300 - 5 * max(0, len(users) - 1)))
