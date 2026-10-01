"""Ephemeral guided voice qualification with bounded capture-gain tuning."""
from __future__ import annotations

import time
import uuid
import math

from .voice import WakeGate, parse_local_command
from .voice_signal import derive_profile

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
        self.room_floors: list[float] = []
        self.audio_profile: dict | None = None
        self.ambient_until = 0.0
        self.ambient_duration = 0.0
        self.ambient_pending = False

    def start(self, now: float | None = None, *, ambient_seconds: float = 0) -> dict:
        now = time.monotonic() if now is None else now
        if not 0 <= ambient_seconds <= 10:
            raise ValueError("Invalid room-noise interval")
        self.session = uuid.uuid4().hex
        self.until = now + 300
        # The clock starts with the first *actual* microphone level report,
        # not the UI tap. A slow service startup must not skip the baseline.
        self.ambient_duration = ambient_seconds
        self.ambient_until = 0.0
        self.ambient_pending = ambient_seconds > 0
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
        self.room_floors = []
        self.audio_profile = None
        self.message = ("Stay quiet while Luma measures room sound."
                        if ambient_seconds else "Wait for the microphone to start, then say the phrase.")
        return self.status(now)

    def status(self, now: float | None = None) -> dict:
        now = time.monotonic() if now is None else now
        active = self.until > now and self.index < len(PHRASES) and self.attempts < 32
        ambient_remaining = (math.ceil(self.ambient_duration) if self.ambient_pending
                             else max(0, math.ceil(self.ambient_until - now))) if active else 0
        recent = active and now - self.last_heard_at <= 15
        floors = sorted(self.room_floors)
        quiet_half = floors[:max(1, len(floors) // 2)]
        candidate = (derive_profile(self.room_floors, self.results).public()
                     if active and not ambient_remaining and len(self.room_floors) >= 3
                     and sum(bool(item.get('acoustic_speech')) for item in self.results) >= 3
                     else None)
        return {
            "session": self.session, "active": active,
            "passed": self.index == len(PHRASES),
            "phrase": PHRASES[self.index] if active and not ambient_remaining else None,
            "ambient_remaining": ambient_remaining,
            "expects_wake": PHRASES[self.index].startswith("hey luma ")
            if active and not ambient_remaining else None,
            "completed": self.index, "total": len(PHRASES), "attempts": self.attempts,
            "message": (("Stay quiet while Luma measures room sound."
                         if ambient_remaining else self.message)
                        if active or self.index == len(PHRASES)
                        else "Start a new check when you are ready."),
            "signal_available": active and self.signal_at > 0 and now - self.signal_at <= 3,
            "signal_rms": self.signal_rms, "signal_peak": self.signal_peak,
            "last_heard": self.last_heard if recent else "",
            "last_free_available": self.last_free_available if recent else False,
            "last_constrained": self.last_constrained if recent else "",
            "last_wake_detected": self.last_wake_detected if recent else None,
            "last_expected_wake": self.last_expected_wake if recent else None,
            "last_intent": self.last_intent if recent else "",
            "last_selection": self.last_selection if recent else "",
            "applied_gain": self.applied_gain,
            "gain_adjustments": self.gain_adjustments,
            "room_noise_rms": round(quiet_half[len(quiet_half)//2], 5)
            if quiet_half else None,
            "audio_profile": self.audio_profile,
            "audio_candidate": candidate,
            "results": list(self.results),
        }

    def gain_step(self, rms: float, peak: float, clipped_fraction: float = 0) -> int:
        """Adjust only obvious level faults; never chase a recognition mismatch.

        A near-zero peak usually means an absent capture route, not low gain.
        Limit the entire session to three reversible four-step hardware moves.
        """
        if self.gain_adjustments >= 3:
            return 0
        if peak >= .995 or clipped_fraction > .002:
            return -4
        if .005 <= peak < .5 and rms < .002:
            if self.room_floors:
                floor = sorted(self.room_floors)[len(self.room_floors) // 2]
                if floor >= max(.004, rms / 3):
                    return 0  # Amplifying this input would mostly raise noise.
            return 4
        return 0

    def record_gain(self, gain: int) -> None:
        self.applied_gain = gain
        self.gain_adjustments += 1
        self.message += f" Capture gain adjusted to {gain} of 63; repeat the phrase."

    def report_level(self, session: str, rms: float, peak: float, now: float | None = None,
                     *, floor_rms: float | None = None) -> dict:
        """Keep only short-lived numeric level data while the owner is calibrating."""
        now = time.monotonic() if now is None else now
        if session != self.session or not self.status(now)["active"]:
            raise ValueError("Calibration session has expired")
        if not (0 <= rms <= 1 and 0 <= peak <= 1
                and (floor_rms is None or 0 <= floor_rms <= 1)):
            raise ValueError("Invalid microphone level")
        if self.ambient_pending:
            self.ambient_until = now + self.ambient_duration
            self.ambient_pending = False
        self.signal_rms = round(rms, 4)
        self.signal_peak = round(peak, 4)
        self.signal_at = now
        if floor_rms is not None and (self.ambient_until == 0 or now <= self.ambient_until):
            self.room_floors.append(floor_rms)
            self.room_floors = self.room_floors[-300:]
        return self.status(now)

    def submit(self, session: str, text: str, rms: float, peak: float, now: float | None = None,
               *, free_text: str = "", selected_text: str | None = None,
               selection: str = "", dc: float = 0.0,
               clipped_fraction: float = 0.0) -> dict:
        now = time.monotonic() if now is None else now
        if session != self.session or not self.status(now)["active"]:
            raise ValueError("Calibration session has expired")
        if self.ambient_pending or now < self.ambient_until:
            return self.status(now)
        if self.index == 0 and self.ambient_until and not self.room_floors:
            self.message = "Room sound was not measured. Restart the check and stay quiet briefly."
            return self.status(now)
        if not 0 <= dc <= 1 or not 0 <= clipped_fraction <= 1:
            raise ValueError("Invalid audio measurements")
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
        floors = sorted(self.room_floors)
        quiet_half = floors[:max(1, len(floors) // 2)]
        noise = quiet_half[len(quiet_half) // 2] if quiet_half else 0.0
        acoustic_speech = (rms >= max(.0005, noise * 2.5)
                           and peak >= max(.005, noise * 4))
        level_ok = .002 <= rms and peak < .995 and clipped_fraction <= .002
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
        self.results.append({"phrase_index": self.index, "matched": matched,
                             "level_ok": level_ok,
                             "acoustic_speech": acoustic_speech,
                             "rms": round(rms, 5), "peak": round(peak, 5),
                             "dc": round(dc, 5),
                             "clipped_fraction": round(clipped_fraction, 5)})
        if matched and level_ok:
            self.index += 1
            self.message = "All voice checks passed. Try again if the room or microphone placement changes." if self.index == len(PHRASES) else "That worked. Say the next phrase."
            if self.index == len(PHRASES):
                self.last_heard = ""
                self.audio_profile = derive_profile(self.room_floors, self.results).public()
                if self.audio_profile['quality'] == 'noisy':
                    self.message += " Room noise is high; Luma left the audio untouched. Recheck placement before relying on voice."
                elif self.audio_profile['quality'] == 'clipped':
                    self.message += " Some speech clipped; lower ReSpeaker capture gain and repeat."
                elif self.audio_profile['quality'] == 'bypass':
                    self.message += " Room sound was not measured well enough to tune processing; audio remains untouched."
        elif peak >= .995 or clipped_fraction > .002:
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
