from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .models import DisplayPower, PrivacyLevel, RuntimeState, Settings


def utc_now() -> datetime:
    return datetime.now(UTC)


class StateMachine:
    def __init__(self, settings: Settings, state: RuntimeState | None = None):
        self.settings = settings
        self.state = state or RuntimeState()

    def phone_seen(self, now: datetime | None = None) -> RuntimeState:
        now = now or utc_now()
        if not self.state.phone_connected:
            self.state.forced_private = False
        self.state.phone_connected = True
        self.state.phone_last_seen_at = now
        return self.evaluate(now)

    def phone_disconnected(self, now: datetime | None = None) -> RuntimeState:
        now = now or utc_now()
        self.state.phone_connected = False
        return self.evaluate(now)

    def unlock_with_pin(self, now: datetime | None = None) -> RuntimeState:
        now = now or utc_now()
        self.state.pin_unlocked_until = now + timedelta(minutes=self.settings.pin_unlock_minutes)
        self.state.forced_private = False
        return self.evaluate(now)

    def force_private(self, now: datetime | None = None) -> RuntimeState:
        now = now or utc_now()
        self.state.forced_private = True
        self.state.pin_unlocked_until = None
        return self.evaluate(now)

    def set_scheduled_sleep(self, end: datetime | None, now: datetime | None = None) -> RuntimeState:
        now = now or utc_now()
        self.state.scheduled_sleep_end = end
        if end is None or end <= now:
            self.state.temporary_wake_until = None
            self.state.morning_override_until = None
        return self.evaluate(now)

    def temporary_wake(self, now: datetime | None = None) -> RuntimeState:
        now = now or utc_now()
        self.state.temporary_wake_until = now + timedelta(
            minutes=self.settings.temporary_night_wake_minutes
        )
        return self.evaluate(now)

    def good_morning(self, now: datetime | None = None) -> RuntimeState:
        now = now or utc_now()
        self.state.forced_sleep_until = None
        self.state.temporary_wake_until = None
        self.state.morning_override_until = self.state.scheduled_sleep_end or (
            now + timedelta(hours=8)
        )
        return self.evaluate(now)

    def good_night(self, now: datetime | None = None) -> RuntimeState:
        now = now or utc_now()
        self.state.morning_override_until = None
        self.state.temporary_wake_until = None
        candidate = self.state.scheduled_sleep_end
        if candidate is None or candidate <= now:
            candidate = now + timedelta(hours=8)
        self.state.forced_sleep_until = candidate
        return self.evaluate(now)

    def evaluate(self, now: datetime | None = None) -> RuntimeState:
        now = now or utc_now()

        phone_recent = self.state.phone_connected
        if not phone_recent and self.state.phone_last_seen_at is not None:
            grace = timedelta(seconds=self.settings.phone_disconnect_grace_seconds)
            phone_recent = now - self.state.phone_last_seen_at < grace

        pin_valid = bool(self.state.pin_unlocked_until and self.state.pin_unlocked_until > now)
        self.state.privacy = (
            PrivacyLevel.FULL
            if not self.state.forced_private and (phone_recent or pin_valid)
            else PrivacyLevel.PRIVATE
        )

        scheduled_sleep = bool(self.state.scheduled_sleep_end and self.state.scheduled_sleep_end > now)
        forced_sleep = bool(self.state.forced_sleep_until and self.state.forced_sleep_until > now)
        temporary_wake = bool(self.state.temporary_wake_until and self.state.temporary_wake_until > now)
        morning_override = bool(
            self.state.morning_override_until and self.state.morning_override_until > now
        )
        should_sleep = (scheduled_sleep and not morning_override) or forced_sleep
        self.state.display_power = (
            DisplayPower.OFF if should_sleep and not temporary_wake else DisplayPower.ON
        )
        self.state.updated_at = now
        return self.state
