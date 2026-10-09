from __future__ import annotations

import asyncio
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Any
from time import monotonic
from secrets import randbelow

from .calendar_logic import active_sleep_end, ongoing_events, todo_events, todo_view, visible_events
from .commands import CommandRouter
from .models import (
    CalendarEvent,
    Command,
    CommandResult,
    DisplayPower,
    PhoneNotification,
    PrivacyLevel,
    RuntimeState,
    WeatherSnapshot,
)
from .serde import (
    calendar_event_from_dict,
    notification_from_dict,
    runtime_state_from_dict,
    settings_from_dict,
    to_primitive,
    weather_from_dict,
)
from .state_machine import StateMachine
from .storage import Storage
from .focus_timer import FocusTimer, TIMER_COMMANDS
from .weather_nudges import weather_nudge
from .departures import Departures
from .display_cycle import DisplayCycle
from .display_handoff import DisplayHandoff
from .countdowns import Countdowns
from .transit import Transit
from .agenda import day_agenda
from .room import Room
from .scenes import Scenes
from .presence_transitions import PresenceTransitions
from .voice_accounts import VoiceAccounts


def display_clock_trusted():
    # Windows is a development preview host, not the delivered Pi. Linux uses
    # a boot-local timesyncd marker, never a persistent "clock was OK" flag.
    return os.name == 'nt' or Path('/run/systemd/timesync/synchronized').is_file()


class LumaService:
    """Owns mutable appliance state and produces privacy-safe UI snapshots."""

    def __init__(self, storage: Storage, *, clock_trusted=display_clock_trusted):
        self.storage = storage
        settings = storage.load_settings()
        raw_runtime = storage.get_cache("runtime", "state")
        runtime = runtime_state_from_dict(raw_runtime) if raw_runtime else RuntimeState()
        self.machine = StateMachine(settings, runtime)
        self.router = CommandRouter(storage, self.machine)
        self.timer = FocusTimer(storage)
        self.departures = Departures(storage)
        self.countdowns = Countdowns(storage)
        self.transit = Transit(storage)
        self.room = Room(storage)
        self.scenes = Scenes(storage)
        self.display = DisplayCycle(storage)
        self.display_handoff = DisplayHandoff()
        self.display_state = None
        self._display_tick_sample = None
        self.display_clock_trusted = clock_trusted
        self.display_bridge_generation = None
        self.events = self._load_events()
        self.weather = self._load_weather()
        self.todo_write_authorized = False
        self.calendar_synced_at: datetime | None = None
        self.calendar_sync_error = False
        self.notifications = self._load_notifications()
        self._pending_notification_chimes: deque[str] = deque(maxlen=20)
        self._seen_notification_chimes: deque[str] = deque(maxlen=256)
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        # Generic feedback never enters the phone notification/chime queue
        # or the saved settings database. No recognized speech is retained.
        self._unknown_command_until = 0.0
        self._unknown_command_id = 0
        self.profiles = self.profile_calendars = self.user_bluetooth = self.personal_timers = None
        self.presence_transitions = PresenceTransitions()
        self.presence_update_busy = False
        self.presence_update_pending = 0
        self.voice_accounts = VoiceAccounts(self)
        self._sync_sleep(datetime.now(UTC))

    def attach_users(self, profiles, bluetooth, calendars):
        """Activate account projections and actual ANCS presence as one unit.

        Legacy flat fields remain primary-only for old callers. The wall uses
        user_panels; a guest connection can never unlock flat primary data.
        """
        from .personal_timers import PersonalTimers
        self.profiles, self.user_bluetooth, self.profile_calendars = profiles, bluetooth, calendars
        self.personal_timers = PersonalTimers(profiles)

    def present_user_ids(self, *, wall=False):
        if self.user_bluetooth is None:
            return set()
        return self.user_bluetooth.present_ids(wall=wall)

    def primary_private_visible(self, now=None, *, briefing=False):
        now = now or datetime.now(UTC)
        self._sync_sleep(now)
        full = self.state.privacy == PrivacyLevel.FULL and (briefing or self.state.display_power == DisplayPower.ON) and (not self.display_state or
            (not self.display_state['awaiting_clock'] and (briefing or self.display_state['mode'] == 'day')))
        pin_valid = self.state.pin_unlocked_until and self.state.pin_unlocked_until > now
        return bool(full and (self.user_bluetooth is None or pin_valid or 'primary' in self.present_user_ids(wall=True)))

    def calendar_is_fresh(self, now):
        legacy_fresh = bool(not self.calendar_sync_error and self.calendar_synced_at and
                            timedelta(0) <= now - self.calendar_synced_at <= timedelta(minutes=10))
        if self.profile_calendars is not None:
            return bool(legacy_fresh and not self.profile_calendars.account('primary').status['error'])
        return legacy_fresh

    @property
    def settings(self):
        return self.machine.settings

    @property
    def state(self):
        return self.machine.state

    def _load_events(self) -> list[CalendarEvent]:
        return [
            calendar_event_from_dict(item)
            for item in (self.storage.get_cache("calendar", "events") or [])
        ]

    def _load_weather(self) -> WeatherSnapshot | None:
        payload = self.storage.get_cache("weather", "forecast")
        return weather_from_dict(payload) if payload else None

    def _load_notifications(self) -> deque[PhoneNotification]:
        # ANCS identifiers and content are valid only for the current connection.
        self.storage.set_cache("phone", "notifications", [])
        return deque(maxlen=20)

    def _sync_sleep(self, now: datetime) -> None:
        previous = to_primitive(self.state)
        sleep_end = active_sleep_end(
            self.events,
            calendar_ids=set(self.settings.sleep_calendar_ids),
            title=self.settings.sleep_event_title,
            now=now,
        )
        self.machine.set_scheduled_sleep(sleep_end, now)
        self._sync_display(now)
        current = to_primitive(self.state)
        # Tick timestamps are volatile. Only meaningful changes should wear the SD.
        previous.pop("updated_at", None)
        current.pop("updated_at", None)
        if previous != current:
            self._persist_runtime()

    def _sync_display(self, now):
        if not self.settings.onboarding_completed:
            # Commissioning must remain usable offline so Wi-Fi can be set up.
            self.display_state = None
            return
        temporary = self.state.temporary_wake_until and self.state.temporary_wake_until > now
        morning = self.state.morning_override_until and self.state.morning_override_until > now
        ends = [end for end in (self.state.forced_sleep_until, None if morning else self.state.scheduled_sleep_end)
                if end and end > now]
        effective_end = max(ends) if ends and not temporary else None
        try:
            trusted = self.display_clock_trusted()
        except OSError:
            trusted = False
        state = self.display.sync(now, sleep_end=effective_end, brightness=self.settings.brightness,
                                  night_brightness=self.settings.night_brightness,
                                  night_clock=self.settings.night_clock_enabled, trusted=trusted)
        power = state['mode'] != 'off'
        target = int(state['night_brightness'] if state['mode']=='night-clock' else state['day_brightness'])
        state['handoff'] = self.display_handoff.prepare(power=power, brightness=target)
        self.display_state = state
        self.state.display_power = DisplayPower.ON if power else DisplayPower.OFF

    def tick(self, now: datetime | None = None) -> None:
        self._sync_sleep(now or datetime.now(UTC))
        self.publish("clock.tick")

    def timer_muted(self):
        # Timer alarms remain audible through scheduled sleep/display-off;
        # only the owner's explicit zero-volume setting suppresses playback.
        return self.settings.volume == 0

    def timer_tick(self, now=None, *, trusted=None):
        self._sync_sleep(now or datetime.now(UTC))
        # HTTP/bridge reads also advance the cycle. Compare with the previous
        # broadcast sample, not the last read, or a polling client can consume
        # the waking→day transition before the kiosk ever hears about it.
        if self.display_state != self._display_tick_sample:
            self._display_tick_sample = self.display_state
            self.publish('display.updated')
        if self.timer.tick(now, trusted=trusted):
            self.publish('timer.updated')
        if self.personal_timers and self.personal_timers.tick(now, trusted=trusted):
            self.publish('user.timer.updated')
        self._presence_tick(now or datetime.now(UTC))

    def _presence_tick(self, now):
        if self.profiles is None:
            return False
        names = {user.id: user.nickname for user in self.profiles.list()}
        alarms = self.timer.snapshot()['status'] == 'complete' or bool(self.personal_timers and
            any(timer['status'] == 'complete' for timer in self.personal_timers.snapshot(set())))
        asleep = any(end and end > now for end in
                     (self.state.scheduled_sleep_end, self.state.forced_sleep_until))
        suppressed = (not self.settings.onboarding_completed or asleep or
                      self.state.display_power != DisplayPower.ON or self.state.forced_private or
                      self.presence_update_busy or self.presence_update_pending > 0 or alarms or
                      bool(self.display_state and (self.display_state['mode'] != 'day' or
                                                   self.display_state['awaiting_clock'])))
        changed = self.presence_transitions.observe(names, self.present_user_ids(), suppressed=suppressed)
        # Snapshot/device polling can reach a debounce deadline first. Publish
        # here too, or that read would consume the edge before the wall hears it.
        if changed:
            self.publish('user.transition.updated')
        return changed

    def claim_timer_chime(self):
        muted = self.timer_muted()
        room = self.timer.claim_chime(muted=muted)
        personal = self.personal_timers.claim_chime(muted=muted) if self.personal_timers else False
        return room or personal

    def _persist_runtime(self) -> None:
        self.storage.set_cache("runtime", "state", self.state)

    def replace_events(self, events: list[CalendarEvent], now: datetime | None = None) -> None:
        self.events = events
        if self.profile_calendars is not None:
            self.profile_calendars.account('primary').events = events
        self.storage.set_cache("calendar", "events", events)
        self._sync_sleep(now or datetime.now(UTC))
        self.publish("calendar.updated")

    def replace_weather(self, weather: WeatherSnapshot) -> None:
        self.weather = weather
        self.storage.set_cache("weather", "forecast", weather)
        self.publish("weather.updated")

    def update_settings(self, updates: dict[str, Any], now: datetime | None = None) -> None:
        payload = to_primitive(self.settings)
        payload.update(updates)
        candidate = settings_from_dict(payload)
        self.storage.save_settings(candidate)
        self.machine.settings = candidate
        if 'brightness' in updates:
            self.display.manual_brightness(now or datetime.now(UTC), candidate.brightness)
        self._sync_sleep(now or datetime.now(UTC))
        self.publish("settings.updated")

    def receive_notification(self, notification: PhoneNotification) -> bool:
        if notification.app_id not in self.settings.notification_app_allowlist:
            return False
        if notification.id not in self._seen_notification_chimes:
            self._seen_notification_chimes.append(notification.id)
            self._pending_notification_chimes.append(notification.id)
        self.notifications = deque((item for item in self.notifications if item.id != notification.id), maxlen=20)
        self.notifications.appendleft(notification)
        self.publish("phone.notification")
        return True

    def remove_notification(self, notification_id: str) -> None:
        self.notifications = deque((item for item in self.notifications if item.id != notification_id), maxlen=20)
        self._pending_notification_chimes = deque(
            (key for key in self._pending_notification_chimes if key != notification_id), maxlen=20)
        self.publish("phone.notification")

    def claim_notification_chime(self, now: datetime | None = None) -> dict[str, Any]:
        """Consume a new local alert once, even if muted or audio is unavailable."""
        now = now or datetime.now(UTC)
        view = self.snapshot(now)
        # This cue may greet a secondary-only household or announce the last
        # person's departure. It carries no calendar/notification content.
        greeting_audible = (self.settings.notification_chime_enabled and
                            self.settings.notification_chime_volume > 0 and self.settings.volume > 0)
        if self.presence_transitions.claim_chime(audible=greeting_audible):
            return {'play': True, 'volume': self.settings.notification_chime_volume}
        audible = (self.primary_private_visible(now) and
                   view['state']['display_power'] == 'on' and
                   self.settings.notification_chime_enabled and
                   self.settings.notification_chime_volume > 0 and self.settings.volume > 0)
        if not audible:
            self._pending_notification_chimes.clear()
        else:
            while self._pending_notification_chimes:
                key = self._pending_notification_chimes.popleft()
                notice = next((item for item in self.notifications if item.id == key), None)
                if notice and timedelta(0) <= now - notice.received_at <= timedelta(seconds=45):
                    return {'play': True, 'volume': self.settings.notification_chime_volume}
        # Claim the reminder even during privacy/night/zero volume so it never
        # announces an old time-to-leave warning after a reconnect or wake.
        fresh = self.calendar_is_fresh(now)
        reminder = self.departures.snapshot(self.events, self.settings, now,
                                            private=False, fresh=fresh)
        new_departure = self.departures.claim_chime(reminder, now)
        return {'play': bool(audible and new_departure),
                'volume': self.settings.notification_chime_volume}

    def execute(self, command: Command, now: datetime | None = None) -> CommandResult:
        now = now or datetime.now(UTC)
        self._sync_sleep(now)
        if command.name.value == 'screen_off' and not self.settings.onboarding_completed:
            return CommandResult(False, 'Finish initial setup before using screen off.')
        if command.name.value in TIMER_COMMANDS:
            self.timer_tick(now)
            result = self.timer.execute(command.name.value, command.value, now=now,
                                        focus=self.settings.timer_focus_minutes, rest=self.settings.timer_break_minutes,
                                        source=command.source)
        else:
            result = self.router.execute(command, now)
        if result.accepted and self.settings.onboarding_completed:
            if command.name.value in {'good_morning','wake'}:
                briefing = self.display.wake(now, morning=command.name.value=='good_morning')
                if command.name.value=='good_morning':
                    result.data['briefing'] = briefing
            elif command.name.value=='good_night':
                self.display.night(now, until=self.state.forced_sleep_until or now+timedelta(hours=8))
            elif command.name.value=='screen_off':
                self.display.off(now)
            elif command.name.value=='set_brightness':
                self.display.manual_brightness(now, self.settings.brightness)
            self._sync_sleep(now)
        if result.state_changed:
            self._persist_runtime()
            self.publish("state.updated")
        if result.accepted:
            self.publish("command.executed", {"name": command.name.value, "page": self.state.active_page.value, **result.data})
        return result

    def phone_seen(self, now: datetime | None = None) -> None:
        was_connected = self.state.phone_connected
        self.machine.phone_seen(now)
        if not was_connected:
            self._persist_runtime()
            self.publish("presence.updated")

    def phone_disconnected(self, now: datetime | None = None) -> None:
        self.machine.phone_disconnected(now)
        self.notifications.clear()
        self._pending_notification_chimes.clear()
        self._persist_runtime()
        self.publish("presence.updated")

    def unlock_with_pin(self, now: datetime | None = None) -> None:
        self.machine.unlock_with_pin(now)
        self._persist_runtime()
        self.publish("privacy.updated")

    def unknown_voice_command(self) -> None:
        # A browser may survive an API restart. A process-local counter would
        # reuse its already-expired id and hide the next legitimate notice.
        self._unknown_command_id = randbelow((1 << 52) - 1) + 1
        self._unknown_command_until = monotonic() + 3
        self.publish("voice.feedback")

    def snapshot(self, now: datetime | None = None, *, briefing=False) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        self._sync_sleep(now)
        full = self.primary_private_visible(now, briefing=briefing)
        self._presence_tick(now)
        present = self.present_user_ids()
        day_visible = not self.state.forced_private and (briefing or self.state.display_power == DisplayPower.ON) and (not self.display_state or
            (not self.display_state['awaiting_clock'] and (briefing or self.display_state['mode'] == 'day')))
        panels = self.profile_calendars.wall_panels(now) if self.profile_calendars and day_visible else []
        panels = [panel for panel in panels if panel['configured']]
        any_private = full or bool(panels)
        state_view = to_primitive(self.state)
        if self.user_bluetooth is not None:
            state_view['privacy'] = 'full' if any_private else 'private'
        settings_view = to_primitive(self.settings)
        if self.profiles is not None and not full:
            # Calendar identifiers/selections also belong to the absent primary.
            from .profiles import personal_settings
            settings_view.update(personal_settings({}))
        roster = [{'profile_id': user.id, 'nickname': user.nickname, 'role': user.role}
                  for user in self.profiles.list() if user.id in present] if self.profiles else []
        selected = set(self.settings.visible_calendar_ids)
        visible = visible_events(self.events, now=now, calendar_ids=selected,
                                 sleep_calendar_ids=set(self.settings.sleep_calendar_ids),
                                 sleep_title=self.settings.sleep_event_title) if full else []
        todos = todo_events(
            self.events,
            todo_calendar_id=self.settings.todo_calendar_id,
            now=now,
        ) if full else []
        notifications = list(self.notifications) if full else []
        weather = to_primitive(self.weather) if self.weather else None
        if weather:
            age = now.astimezone(UTC) - self.weather.observed_at.astimezone(UTC)
            weather["stale"] = self.weather.stale or age > timedelta(hours=2) or age < timedelta(0)
            weather["nudge"] = weather_nudge(self.weather, self.settings, now)
            weather["hourly"] = [hour for hour in weather["hourly"] if datetime.fromisoformat(hour["time"]) >= now.replace(minute=0, second=0, microsecond=0)]
        calendar_fresh = self.calendar_is_fresh(now)
        return {
            "server_time": now.isoformat(),
            "presence_transition": self.presence_transitions.view(
                {user.id: user.nickname for user in self.profiles.list()}) if self.profiles else None,
            "voice_account_choice": self.voice_accounts.view(now),
            "voice_notice": {"id": self._unknown_command_id,
                             "remaining_ms": max(0, int((self._unknown_command_until - monotonic()) * 1000))},
            "room": self.room.view(now) if full else None,
            "countdowns": self.countdowns.snapshot(now,private=not full,
                quiet=bool(self.display_state and (self.display_state['mode']!='day' or self.display_state['awaiting_clock']))),
            "transit": self.transit.snapshot(now,private=not full,
                quiet=bool(self.display_state and (self.display_state['mode']!='day' or self.display_state['awaiting_clock']))),
            "display": self.display_state,
            "settings": settings_view,
            "state": state_view,
            "users": roster,
            "user_panels": panels,
            "personal_timers": self.personal_timers.snapshot(self.present_user_ids(wall=True) if day_visible else set()) if self.personal_timers else [],
            "weather": weather,
            "calendar": to_primitive(visible),
            "agenda": day_agenda(self.events, self.settings, now, fresh=calendar_fresh) if full else None,
            "ongoing": to_primitive(ongoing_events(visible, now)),
            "todos": sorted([todo_view(event, self.settings.todo_completed_color_id) for event in todos],
                            key=lambda item: (item["completed"], item["due_date"], item["summary"].casefold(), item["id"])),
            "todo_controls": {"can_update": bool(full and self.todo_write_authorized and self.settings.todo_calendar_id and self.settings.todo_completed_color_id
                                                   and any(event.calendar_writable for event in todos)),
                              "stale": not calendar_fresh},
            "notifications": to_primitive(notifications),
            "privacy_redacted": not any_private,
            "primary_privacy_redacted": not full,
            "timer": self.timer.snapshot(private=not full),
            "departure": self.departures.snapshot(self.events,self.settings,now,private=not full,fresh=calendar_fresh),
        }

    def voice_snapshot(self, *, authorized: bool, now: datetime | None = None):
        """Questions include earlier-today events, but never bypass privacy."""
        now = now or datetime.now(UTC)
        snapshot = self.snapshot(now)
        # Until a specific voice account has been chosen, never let the fact
        # that a guest has a visible panel authorize the primary's flat data.
        if self.user_bluetooth is not None and snapshot['primary_privacy_redacted']:
            snapshot['privacy_redacted'] = True
        start = now.astimezone(ZoneInfo(self.settings.timezone)).replace(hour=0, minute=0, second=0, microsecond=0)
        events = visible_events(self.events, now=start, calendar_ids=set(self.settings.visible_calendar_ids),
                                sleep_calendar_ids=set(self.settings.sleep_calendar_ids),
                                sleep_title=self.settings.sleep_event_title) if not snapshot['privacy_redacted'] else []
        snapshot['voice_calendar'] = {
            'authorized': authorized,
            'fresh': self.calendar_is_fresh(now),
            'events': to_primitive([event for event in events if not event.self_declined]),
        }
        snapshot['voice_todos'] = to_primitive(sorted(
            (todo_view(event, self.settings.todo_completed_color_id) for event in self.events
             if not snapshot['privacy_redacted'] and event.calendar_id == self.settings.todo_calendar_id
             and event.all_day and event.status != 'cancelled'),
            key=lambda item: (item['due_date'], item['summary'].casefold()),
        )[:100])
        return snapshot

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=4)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def publish(self, reason: str, action: dict[str, Any] | None = None) -> None:
        message = {"type": reason}
        if action:
            message["action"] = action
        for queue in tuple(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(message)
