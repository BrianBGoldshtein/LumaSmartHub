from __future__ import annotations

import subprocess
import unittest

from luma.hardware import AudioController, DisplayController
from luma.models import CommandName, Page, Theme
from luma.voice import parse_local_command


class VoiceTests(unittest.TestCase):
    def test_local_commands(self) -> None:
        cases = {
            "Hey Luma, brightness 35": (CommandName.SET_BRIGHTNESS, 35),
            "Luma show my forecast": (CommandName.SHOW_PAGE, Page.WEATHER),
            "change the theme to cabin": (CommandName.SET_THEME, Theme.HEARTH),
            "good night": (CommandName.GOOD_NIGHT, None),
            "hide my private details": (CommandName.PRIVACY_NOW, None),
        }
        for transcript, expected in cases.items():
            with self.subTest(transcript=transcript):
                result = parse_local_command(transcript)
                self.assertIsNotNone(result)
                self.assertEqual((result.name, result.value), expected)

    def test_unknown_phrase_stays_local_and_does_not_guess(self) -> None:
        self.assertIsNone(parse_local_command("Hey Luma, make everything magical"))


class HardwareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: list[list[str]] = []

        def runner(args):
            self.calls.append(list(args))
            return subprocess.CompletedProcess(args, 0, "", "")

        self.runner = runner

    def test_display_and_audio_use_argument_arrays(self) -> None:
        display = DisplayController("HDMI-A-1", self.runner)
        audio = AudioController(self.runner)

        display.power(False)
        display.set_orientation("portrait-clockwise")
        audio.set_volume(45)

        self.assertEqual(self.calls[0], ["wlr-randr", "--output", "HDMI-A-1", "--off"])
        self.assertEqual(self.calls[1][-1], "90")
        self.assertEqual(self.calls[2][-1], "45%")

    def test_audio_sink_rejects_command_injection(self) -> None:
        with self.assertRaises(ValueError):
            AudioController(self.runner).set_default_sink("2; shutdown")


if __name__ == "__main__":
    unittest.main()
