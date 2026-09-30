from __future__ import annotations

import subprocess
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def run_checked(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(arguments, check=True, capture_output=True, text=True, timeout=8)


@dataclass(slots=True)
class DisplayController:
    output_name: str = "HDMI-A-1"
    runner: Runner = run_checked

    def power(self, on: bool) -> None:
        self.runner(["wlr-randr", "--output", self.output_name, "--on" if on else "--off"])

    def set_brightness(self, percentage: int) -> bool:
        if not 0 <= percentage <= 100:
            raise ValueError("brightness must be between 0 and 100")
        try:
            self.runner(["ddcutil", "setvcp", "10", str(percentage), "--noverify"])
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            # Some portable HDMI panels do not expose DDC/CI. Settings still persist,
            # and diagnostics makes the unsupported hardware control explicit.
            return False

    def set_brightness_confirmed(self, percentage: int) -> bool:
        """Read the panel's VCP scale and verify it before releasing the dimmer.

        ddcutil's terse continuous response is: VCP 10 C <current> <maximum>.
        Floor conversion never claims a lower reference than the raw target.
        An unsupported/ambiguous readback keeps the software fallback active.
        """
        if type(percentage) is not int or not 0 <= percentage <= 100:
            raise ValueError('brightness must be a whole percentage')
        def read():
            result = self.runner(['ddcutil','getvcp','10','--terse'])
            match = re.fullmatch(r'VCP\s+10\s+C\s+([0-9]+)\s+([0-9]+)', result.stdout.strip())
            if not match:
                raise ValueError('Unsupported brightness readback')
            current, maximum = map(int,match.groups())
            if not 0 <= current <= maximum <= 65535 or maximum == 0:
                raise ValueError('Invalid brightness scale')
            return current, maximum
        try:
            _, maximum = read()
            target = percentage * maximum // 100
            # Default ddcutil verification stays enabled, followed by our own
            # scale-aware check. Each subprocess has the existing 8s timeout.
            self.runner(['ddcutil','setvcp','10',str(target)])
            actual, confirmed_maximum = read()
            return confirmed_maximum == maximum and actual == target
        except (OSError, ValueError, subprocess.SubprocessError):
            return False

    def set_orientation(self, transform: str) -> None:
        mapping = {"landscape": "normal", "portrait-clockwise": "90", "portrait-counterclockwise": "270"}
        self.runner(["wlr-randr", "--output", self.output_name, "--transform", mapping[transform]])


@dataclass(slots=True)
class AudioController:
    runner: Runner = run_checked

    def set_output(self, mode: str) -> bool:
        if mode == "auto":
            return True  # Respect the desktop's chosen default.
        if mode not in {"hdmi", "hat"}:
            raise ValueError("audio output must be auto, hdmi, or hat")
        sinks = json.loads(self.runner(["pactl", "--format=json", "list", "sinks"]).stdout)
        terms = ("hdmi",) if mode == "hdmi" else ("wm8960", "respeaker", "seeed")
        matches = [sink for sink in sinks if any(term in json.dumps(sink.get("properties", {})).lower() + sink.get("name", "").lower() for term in terms)]
        if len(matches) != 1:
            return False  # Never guess between multiple physical outputs.
        self.runner(["pactl", "set-default-sink", matches[0]["name"]])
        return True

    def set_volume(self, percentage: int) -> None:
        if not 0 <= percentage <= 100:
            raise ValueError("volume must be between 0 and 100")
        self.runner(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{percentage}%"])

    def set_default_sink(self, node_id: str) -> None:
        if not node_id.isdigit():
            raise ValueError("PipeWire node ID must be numeric")
        self.runner(["wpctl", "set-default", node_id])


@dataclass(slots=True)
class VoiceController:
    runner: Runner = run_checked

    def set_enabled(self, enabled: bool) -> bool:
        self.runner(["systemctl", "--user", "start" if enabled else "stop", "luma-voice.service"])
        if enabled:
            return self.runner(["systemctl", "--user", "is-active", "luma-voice.service"]).stdout.strip() == "active"
        return True
