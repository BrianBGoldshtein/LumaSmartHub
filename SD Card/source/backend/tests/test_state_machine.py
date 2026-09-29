from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from luma.models import DisplayPower, PrivacyLevel, Settings
from luma.state_machine import StateMachine


NOW = datetime(2026, 9, 24, 8, 0, tzinfo=UTC)


class StateMachineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(
            phone_disconnect_grace_seconds=45,
            pin_unlock_minutes=15,
            temporary_night_wake_minutes=5,
        )
        self.machine = StateMachine(self.settings)

    def test_phone_presence_unlocks_and_grace_avoids_flicker(self) -> None:
        state = self.machine.phone_seen(NOW)
        self.assertEqual(state.privacy, PrivacyLevel.FULL)

        self.machine.phone_disconnected(NOW + timedelta(seconds=10))
        self.assertEqual(self.machine.evaluate(NOW + timedelta(seconds=44)).privacy, PrivacyLevel.FULL)
        self.assertEqual(self.machine.evaluate(NOW + timedelta(seconds=45)).privacy, PrivacyLevel.PRIVATE)

    def test_pin_temporarily_unlocks_private_content(self) -> None:
        self.machine.unlock_with_pin(NOW)

        self.assertEqual(self.machine.evaluate(NOW + timedelta(minutes=14)).privacy, PrivacyLevel.FULL)
        self.assertEqual(self.machine.evaluate(NOW + timedelta(minutes=15)).privacy, PrivacyLevel.PRIVATE)

    def test_privacy_now_overrides_a_connected_phone(self) -> None:
        self.machine.phone_seen(NOW)
        state = self.machine.force_private(NOW + timedelta(seconds=1))

        self.assertEqual(state.privacy, PrivacyLevel.PRIVATE)

    def test_sleep_event_turns_off_display_and_temporary_wake_expires(self) -> None:
        sleep_end = NOW + timedelta(hours=8)
        self.machine.set_scheduled_sleep(sleep_end, NOW)
        self.assertEqual(self.machine.state.display_power, DisplayPower.OFF)

        self.machine.temporary_wake(NOW + timedelta(minutes=1))
        self.assertEqual(self.machine.state.display_power, DisplayPower.ON)
        self.assertEqual(
            self.machine.evaluate(NOW + timedelta(minutes=6)).display_power,
            DisplayPower.OFF,
        )

    def test_good_morning_overrides_the_active_sleep_event(self) -> None:
        sleep_end = NOW + timedelta(hours=3)
        self.machine.set_scheduled_sleep(sleep_end, NOW)

        state = self.machine.good_morning(NOW + timedelta(minutes=1))

        self.assertEqual(state.display_power, DisplayPower.ON)
        self.assertEqual(
            self.machine.evaluate(sleep_end + timedelta(seconds=1)).display_power,
            DisplayPower.ON,
        )

    def test_good_night_without_calendar_sleeps_for_eight_hours(self) -> None:
        self.machine.good_night(NOW)

        self.assertEqual(self.machine.state.display_power, DisplayPower.OFF)
        self.assertEqual(
            self.machine.evaluate(NOW + timedelta(hours=8)).display_power,
            DisplayPower.ON,
        )


if __name__ == "__main__":
    unittest.main()
