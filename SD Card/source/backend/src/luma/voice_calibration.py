"""Ephemeral guided voice qualification with bounded capture-gain tuning."""
from __future__ import annotations

import time
import uuid

from .voice import WakeGate, parse_local_command

PHRASES = (
    "hey luma set brightness to fifty",
    "hey luma set volume to fifty",
    "hey luma change theme to arcade",
    "hey luma what time is it",
    "hey luma good morning",
    "hey luma what's the weather tomorrow",
    "hey luma what's the time",
    "hey luma when is my next event",
    "what time is it",
    "good morning",
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
        self.last_heard = ""
        self.last_free_available = False
        self.last_constrained = ""
        self.last_heard_at = 0.0
        self.last_wake_detected = False
        self.last_expected_wake = True
        self.last_intent = ""
        self.last_selection = ""
        self.applied_gain: int | None = None
        self.gain_adjustments = 0

    def start(self, now: float | None = None) -> dict:
        now = time.monotonic() if now is None else now
        self.session = uuid.uuid4().hex
        self.until = now + 300
        self.index = self.attempts = 0
        self.results = []
        self.signal_rms = self.signal_peak = self.signal_at = 0.0
        self.last_heard = ""
        self.last_free_available = False
        self.last_constrained = ""
        self.last_heard_at = 0.0
        self.last_wake_detected = False
        self.last_expected_wake = True
        self.last_intent = ""
        self.last_selection = ""
        self.applied_gain = None
        self.gain_adjustments = 0
        self.message = "Wait for the microphone to start, then say the phrase."
        return self.status(now)

    def status(self, now: float | None = None) -> dict:
        now = time.monotonic() if now is None else now
        active = self.until > now and self.index < len(PHRASES) and self.attempts < 32
        recent = active and now - self.last_heard_at <= 15
        return {"session": self.session, "active": active, "passed": self.index == len(PHRASES), "phrase": PHRASES[self.index] if active else None, "expects_wake": PHRASES[self.index].startswith("hey luma ") if active else None, "completed": self.index, "total": len(PHRASES), "attempts": self.attempts, "message": self.message if active or self.index == len(PHRASES) else "Start a new check when you are ready.", "signal_available": active and self.signal_at > 0 and now - self.signal_at <= 3, "signal_rms": self.signal_rms, "signal_peak": self.signal_peak, "last_heard": self.last_heard if recent else "", "last_free_available": self.last_free_available if recent else False, "last_constrained": self.last_constrained if recent else "", "last_wake_detected": self.last_wake_detected if recent else None, "last_expected_wake": self.last_expected_wake if recent else None, "last_intent": self.last_intent if recent else "", "last_selection": self.last_selection if recent else "", "applied_gain": self.applied_gain, "gain_adjustments": self.gain_adjustments, "results": list(self.results)}

    def gain_step(self, rms: float, peak: float) -> int:
        """Adjust only obvious level faults; never chase a recognition mismatch.

        A near-zero peak usually means an absent capture route, not low gain.
        Limit the entire session to three reversible four-step hardware moves.
        """
        if self.gain_adjustments >= 3:
            return 0
        if peak >= .995:
            return -4
        if .005 <= peak < .5 and rms < .002:
            return 4
        return 0

    def record_gain(self, gain: int) -> None:
        self.applied_gain = gain
        self.gain_adjustments += 1
        self.message += f" Capture gain adjusted to {gain} of 63; repeat the phrase."

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

    def submit(self, session: str, text: str, rms: float, peak: float, now: float | None = None,
               *, free_text: str = "", selected_text: str | None = None,
               selection: str = "") -> dict:
        now = time.monotonic() if now is None else now
        if session != self.session or not self.status(now)["active"]:
            raise ValueError("Calibration session has expired")
        accepted = WakeGate().accept(text, now)
        # A live decoder conflict deliberately selects nothing. Only legacy
        # direct samples without selection metadata fall back to the wake pass.
        command_text = selected_text if selected_text is not None else (accepted if not selection else None)
        command = parse_local_command(command_text) if accepted is not None and command_text else None
        expected = parse_local_command(PHRASES[self.index])
        expects_wake = PHRASES[self.index].startswith("hey luma ")
        if expects_wake:
            matched = bool(command and expected and (command.name, command.value) == (expected.name, expected.value))
        else:
            # A negative-control phrase must be recognized as speech but never
            # activate the wake gate or select a command for execution.
            heard = parse_local_command(free_text or text) if accepted is None else None
            matched = bool(heard and expected and selected_text is None
                           and (heard.name, heard.value) == (expected.name, expected.value))
        level_ok = .002 <= rms and peak < .995
        self.attempts += 1
        # Only the live local setup page can see this short-lived transcript.
        # Persistent results retain numeric levels and matches, never speech.
        self.last_heard = (free_text or text)[:160]
        self.last_free_available = bool(free_text)
        self.last_constrained = text[:160] if free_text else ""
        self.last_heard_at = now
        self.last_wake_detected = accepted is not None
        self.last_expected_wake = expects_wake
        self.last_selection = selection
        if command:
            value = getattr(command.value, "value", command.value)
            self.last_intent = (f"{command.name.value}: {value}" if value is not None
                                else command.name.value)
        else:
            self.last_intent = ""
        # Aggregate levels/results only, never transcripts or audio samples.
        self.results.append({"phrase_index": self.index, "matched": matched, "rms": round(rms, 4), "peak": round(peak, 4)})
        if matched and level_ok:
            self.index += 1
            self.message = "All voice checks passed. Try again if the room or microphone placement changes." if self.index == len(PHRASES) else "That worked. Say the next phrase."
            if self.index == len(PHRASES):
                self.last_heard = ""
        elif peak >= .995:
            self.message = "The microphone signal is near clipping. Lower its capture gain and repeat."
        elif rms < .002:
            self.message = "The signal is very quiet. Check the microphone, move closer, or raise capture gain."
        elif not expects_wake and accepted is not None:
            self.message = "False wake detected on a phrase without Hey Luma. Repeat it at normal volume."
        elif not expects_wake:
            self.message = "No wake was activated, but I heard different words. Repeat the displayed phrase."
        elif accepted is None:
            self.message = "I heard speech, but not Hey Luma. Repeat the wake phrase clearly."
        elif selection == "conflict":
            self.message = "The two offline decoders disagreed. No command was selected; repeat clearly."
        elif selection == "negated":
            self.message = "A negation was heard. No command was selected; repeat the displayed phrase."
        elif command is None:
            self.message = "I heard Hey Luma, but not a supported command. Try the displayed words again."
        else:
            self.message = "I heard Hey Luma and a different command. Pause, then repeat the displayed words."
        return self.status(now)

    def cancel(self) -> None:
        self.until = 0
        self.last_heard = ""
        self.last_free_available = False
        self.last_constrained = ""
        self.last_wake_detected = False
        self.last_expected_wake = True
        self.last_intent = ""
        self.last_selection = ""
