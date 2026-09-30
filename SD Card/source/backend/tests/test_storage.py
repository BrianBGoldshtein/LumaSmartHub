from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from luma.models import Orientation, Theme
from luma.storage import Storage
from luma.serde import settings_from_dict


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.storage = Storage(self.root / "luma.db")

    def test_default_settings_are_created_and_valid(self) -> None:
        settings = self.storage.load_settings()

        self.assertEqual(settings.device_name, "Luma")
        self.assertEqual(settings.theme, Theme.LUMA_GLASS)
        self.assertTrue(settings.voice_enabled)
        self.assertTrue(self.storage.integrity_check())

    def test_legacy_settings_do_not_silently_enable_microphone(self) -> None:
        self.assertFalse(settings_from_dict({"device_name": "Older Luma"}).voice_enabled)
        self.assertFalse(settings_from_dict({"voice_enabled": False}).voice_enabled)
        self.assertTrue(settings_from_dict({"voice_enabled": True}).voice_enabled)

    def test_settings_round_trip_enums_and_lists(self) -> None:
        settings = self.storage.load_settings()
        settings.theme = Theme.HEARTH
        settings.orientation = Orientation.PORTRAIT_CLOCKWISE
        settings.visible_calendar_ids = ["primary", "family"]
        self.storage.save_settings(settings)

        restored = Storage(self.root / "luma.db").load_settings()

        self.assertEqual(restored.theme, Theme.HEARTH)
        self.assertEqual(restored.orientation, Orientation.PORTRAIT_CLOCKWISE)
        self.assertEqual(restored.visible_calendar_ids, ["primary", "family"])

    def test_cache_expiry_can_fall_back_to_stale_data(self) -> None:
        expired = datetime.now(UTC) - timedelta(minutes=1)
        self.storage.set_cache("weather", "current", {"temperature": 21}, expires_at=expired)

        self.assertIsNone(self.storage.get_cache("weather", "current", allow_expired=False))
        self.assertEqual(
            self.storage.get_cache("weather", "current", allow_expired=True),
            {"temperature": 21},
        )

    def test_backup_is_a_valid_independent_database(self) -> None:
        settings = self.storage.load_settings()
        settings.brightness = 42
        self.storage.save_settings(settings)

        backup_path = self.storage.backup(self.root / "backups" / "luma.db")
        backup = Storage(backup_path)

        self.assertTrue(backup.integrity_check())
        self.assertEqual(backup.load_settings().brightness, 42)

    def test_invalid_setting_is_not_persisted(self) -> None:
        settings = self.storage.load_settings()
        settings.brightness = 101

        with self.assertRaisesRegex(ValueError, "brightness"):
            self.storage.save_settings(settings)

        self.assertEqual(self.storage.load_settings().brightness, 70)


if __name__ == "__main__":
    unittest.main()
