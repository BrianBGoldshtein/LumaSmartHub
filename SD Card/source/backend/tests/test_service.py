from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from luma.models import CalendarEvent, PhoneNotification, PrivacyLevel, WeatherSnapshot
from luma.service import LumaService
from luma.storage import Storage


NOW = datetime(2026, 9, 24, 16, 30, tzinfo=UTC)


class LumaServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.storage = Storage(Path(self.temporary_directory.name) / "luma.db")
        settings = self.storage.load_settings()
        settings.visible_calendar_ids = ["primary"]
        settings.todo_calendar_id = "todos"
        settings.sleep_calendar_ids = ["primary"]
        self.storage.save_settings(settings)
        self.service = LumaService(self.storage)

    def test_private_snapshot_redacts_calendar_todos_and_notifications(self) -> None:
        self.service.replace_events(
            [
                CalendarEvent("1", "primary", "Private meeting", NOW, NOW + timedelta(hours=1)),
                CalendarEvent("2", "todos", "Private task", NOW, NOW + timedelta(hours=1)),
            ],
            NOW,
        )
        self.service.receive_notification(
            PhoneNotification(
                "n1",
                "net.whatsapp.WhatsApp",
                "WhatsApp",
                "Alice",
                "Private text",
                NOW,
            )
        )

        snapshot = self.service.snapshot(NOW)

        self.assertTrue(snapshot["privacy_redacted"])
        self.assertEqual(snapshot["calendar"], [])
        self.assertEqual(snapshot["todos"], [])
        self.assertEqual(snapshot["notifications"], [])

    def test_phone_presence_reveals_selected_private_content(self) -> None:
        meeting = CalendarEvent("1", "primary", "Meeting", NOW, NOW + timedelta(hours=1))
        self.service.replace_events([meeting], NOW)
        self.service.phone_seen(NOW)

        snapshot = self.service.snapshot(NOW)

        self.assertFalse(snapshot["privacy_redacted"])
        self.assertEqual(snapshot["state"]["privacy"], PrivacyLevel.FULL.value)
        self.assertEqual(snapshot["calendar"][0]["summary"], "Meeting")

    def test_sleep_event_drives_display_power(self) -> None:
        sleep = CalendarEvent(
            "sleep",
            "primary",
            "Sleep",
            NOW - timedelta(hours=1),
            NOW + timedelta(hours=7),
        )

        self.service.replace_events([sleep], NOW)

        self.assertEqual(self.service.snapshot(NOW)["state"]["display_power"], "off")

    def test_cached_data_and_runtime_survive_restart_but_phone_unlock_does_not(self) -> None:
        weather = WeatherSnapshot(NOW, 71, 70, 75, 60, 0, "Clear")
        self.service.replace_weather(weather)
        self.service.phone_seen(NOW)

        restarted = LumaService(self.storage)
        snapshot = restarted.snapshot(NOW + timedelta(seconds=1))

        self.assertEqual(snapshot["weather"]["temperature"], 71)
        self.assertTrue(snapshot["privacy_redacted"])

    def test_disallowed_notification_is_not_stored(self) -> None:
        notification = PhoneNotification(
            "n1",
            "com.example.unselected",
            "Noisy app",
            "Title",
            "Body",
            NOW,
        )

        self.assertFalse(self.service.receive_notification(notification))
        self.service.phone_seen(NOW)
        self.assertEqual(self.service.snapshot(NOW)["notifications"], [])


if __name__ == "__main__":
    unittest.main()
