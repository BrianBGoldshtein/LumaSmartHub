"""Explicit, bounded native keyboard sessions; never accepts text to type."""
from __future__ import annotations

import signal
import subprocess
from time import monotonic


# Fixed palettes only. No caller-supplied executable, flags, font or keystrokes.
PALETTES = {
    "luma-glass": ("10191b", "182326", "a9dfce", "f6f5f0", "DejaVu Sans 22", "8"),
    "hearth": ("231c16", "30271f", "eabf83", "f7ecd8", "DejaVu Serif 22", "8"),
    "neon-grid": ("121322", "1b1d31", "a1e8d8", "f6f2ff", "DejaVu Sans Mono 22", "0"),
}


class SystemKeyboard:
    def __init__(self, launch=subprocess.Popen, clock=monotonic):
        self.launch, self.clock = launch, clock
        self.process = None
        self.last_request = None
        self.deadline = 0.0
        self.theme = None
        self.failed = False

    def status(self):
        exited = self.process is not None and self.process.poll() is not None
        return "unavailable; retrying" if self.failed or exited else "ok"

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=1)
            self.process = None
        self.deadline = 0.0

    def tick(self, awake=True):
        if not awake or (self.process is not None and self.clock() >= self.deadline):
            self.close()

    def apply(self, request: dict, theme: str, awake: bool):
        request_id = request.get("id")
        self.tick(awake)
        if not request_id or request_id == self.last_request:
            return
        # Consume even asleep: an old request must not reopen after waking.
        self.last_request = request_id
        if not awake or not request.get("visible"):
            self.close()
            return
        theme = theme if theme in PALETTES else "luma-glass"
        if self.process is not None and (self.process.poll() is not None or self.theme != theme):
            self.close()
        if self.process is None:
            bg, key, accent, text, font, rounding = PALETTES[theme]
            self.failed = True  # Remains visible in diagnostics if launch fails.
            self.process = self.launch([
                "/opt/luma/bin/luma-keyboard", "-H", "320", "-L", "280", "-R", rounding,
                "--fn", font, "--bg", bg, "--fg", key, "--fg-sp", key,
                "--text", text, "--text-sp", text, "--press", accent, "--press-sp", accent,
            ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.theme = theme
        else:
            # Polling the same request cannot fight the keyboard's own Hide.
            self.process.send_signal(signal.SIGUSR2)
        self.deadline = self.clock() + 900
        self.failed = False
