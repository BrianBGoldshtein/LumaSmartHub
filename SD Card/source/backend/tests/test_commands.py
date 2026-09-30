from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from luma.commands import CommandRouter
from luma.models import Command, CommandName, DisplayPower, Page, Settings, Theme
from luma.state_machine import StateMachine
from luma.storage import Storage


NOW = datetime(2026, 9, 24, 16, 30, tzinfo=UTC)


class CommandRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.storage = Storage(Path(self.temporary_directory.name) / "luma.db")
        self.machine = StateMachine(self.storage.load_settings())
        self.router = CommandRouter(self.storage, self.machine)

    def test_brightness_and_theme_changes_are_persisted(self) -> None:
        brightness = self.router.execute(Command(CommandName.SET_BRIGHTNESS, 31), NOW)
        theme = self.router.execute(Command(CommandName.SET_THEME, Theme.NEON_GRID), NOW)

        settings = self.storage.load_settings()
        self.assertTrue(brightness.accepted)
        self.assertTrue(theme.accepted)
        self.assertEqual(settings.brightness, 31)
        self.assertEqual(settings.theme, Theme.NEON_GRID)

    def test_percentage_range_is_enforced(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 0 and 100"):
            self.router.execute(Command(CommandName.SET_VOLUME, -1), NOW)

    def test_page_navigation_wraps(self) -> None:
        self.machine.state.active_page = Page.HOME
        self.router.execute(Command(CommandName.PREVIOUS_PAGE), NOW)
        self.assertEqual(self.machine.state.active_page, Page.TRANSIT)

        self.router.execute(Command(CommandName.NEXT_PAGE), NOW)
        self.assertEqual(self.machine.state.active_page, Page.HOME)

    def test_good_night_and_good_morning_commands_change_display_state(self) -> None:
        self.router.execute(Command(CommandName.GOOD_NIGHT), NOW)
        self.assertEqual(self.machine.state.display_power, DisplayPower.OFF)

        result = self.router.execute(Command(CommandName.GOOD_MORNING), NOW)
        self.assertEqual(self.machine.state.display_power, DisplayPower.ON)
        self.assertTrue(result.data["briefing"])

    def test_cloud_question_is_disabled_by_default(self) -> None:
        result = self.router.execute(Command(CommandName.ASK, "What is today?"), NOW)

        self.assertFalse(result.accepted)
        self.assertIn("not configured", result.message)

    def test_cloud_question_uses_injected_provider(self) -> None:
        settings = Settings(cloud_provider="test")
        router = CommandRouter(
            self.storage,
            StateMachine(settings),
            cloud_ask=lambda question: f"answer:{question}",
        )

        result = router.execute(Command(CommandName.ASK, "Why?"), NOW)

        self.assertTrue(result.accepted)
        self.assertEqual(result.message, "answer:Why?")


if __name__ == "__main__":
    unittest.main()
