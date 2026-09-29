"""Ephemeral guided voice qualification. Does not train a model or retain audio."""
from __future__ import annotations

import time
import uuid

from .voice import WakeGate, parse_local_command

PHRASES = (
    "hey luma set brightness to fifty",
    "hey luma set volume to fifty",
    "hey luma change theme to arcade",
)


class VoiceCalibration:
    def __init__(self):
        self.session = ""
        self.until = 0.0
        self.index = 0
        self.attempts = 0
        self.message = "Speak from your usual distance in the room."
        self.results: list[dict] = []
        self.signal_rms = 0.0
        self.signal_peak = 0.0
        self.signal_at = 0.0

    def start(self, now: float | None = None) -> dict:
        now = time.monotonic() if now is None else now
        self.session = uuid.uuid4().hex
        self.until = now + 120
        self.index = self.attempts = 0
        self.results = []
        self.signal_rms = self.signal_peak = self.signal_at = 0.0
        self.message = "Wait for the microphone to start, then say the phrase."
        return self.status(now)

    def status(self, now: float | None = None) -> dict:
        now = time.monotonic() if now is None else now
        active = self.until > now and self.index < len(PHRASES) and self.attempts < 12
        return {"session": self.session, "active": active, "passed": self.index == len(PHRASES), "phrase": PHRASES[self.index] if active else None, "completed": self.index, "total": len(PHRASES), "attempts": self.attempts, "message": self.message if active or self.index == len(PHRASES) else "Start a new check when you are ready.", "signal_available": active and self.signal_at > 0 and now - self.signal_at <= 3, "signal_rms": self.signal_rms, "signal_peak": self.signal_peak, "results": list(self.results)}

    def report_level(self, session: str, rms: float, peak: float, now: float | None = None) -> dict:
        """Keep only short-lived numeric level data while the owner is calibrating."""
        now = time.monotonic() if now is None else now
        if session != self.session or not self.status(now)["active"]:
            raise ValueError("Calibration session has expired")
        if not (0 <= rms <= 1 and 0 <= peak <= 1):
            raise ValueError("Invalid microphone level")
        self.signal_rms = round(rms, 4)
        self.signal_peak = round(peak, 4)
        self.signal_at = now
        return self.status(now)

    def submit(self, session: str, text: str, rms: float, peak: float, now: float | None = None) -> dict:
        now = time.monotonic() if now is None else now
        if session != self.session or not self.status(now)["active"]:
            raise ValueError("Calibration session has expired")
        accepted = WakeGate().accept(text, now)
        command = parse_local_command(accepted) if accepted else None
        expected = parse_local_command(PHRASES[self.index])
        matched = bool(command and expected and (command.name, command.value) == (expected.name, expected.value))
        level_ok = .002 <= rms and peak < .995
        self.attempts += 1
        # Aggregate levels/results only, never transcripts or audio samples.
        self.results.append({"phrase_index": self.index, "matched": matched, "rms": round(rms, 4), "peak": round(peak, 4)})
        if matched and level_ok:
            self.index += 1
            self.message = "All three checks passed. Try again if the room or microphone placement changes." if self.index == len(PHRASES) else "That worked. Say the next phrase."
        elif peak >= .995:
            self.message = "The microphone signal is near clipping. Lower its capture gain and repeat."
        elif rms < .002:
            self.message = "The signal is very quiet. Check the microphone, move closer, or raise capture gain."
        else:
            self.message = "That phrase did not match. Pause, then repeat it clearly."
        return self.status(now)

    def cancel(self) -> None:
        self.until = 0
