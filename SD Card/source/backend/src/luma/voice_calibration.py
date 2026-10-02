"""Ephemeral guided voice qualification with bounded capture-gain tuning."""
from __future__ import annotations

import time
import uuid
import math
import re
from statistics import median

from .voice import WakeGate, parse_local_command
from .voice_signal import (AudioProfile, CALIBRATION_MIN_PEAK, CALIBRATION_MIN_RMS,
                           derive_profile, room_noise_level)
from .voice_wake import command_after_wake, wake_near_start
from .voice_adaptation import LEARNABLE, conflicts_with_existing_command, normalized_phrase

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


def word_match_fraction(expected: str, heard: str) -> float | None:
    """Bounded word accuracy for a prompted sample; no transcript is saved.

    This is transcription quality, not intent correctness. A paraphrase can
    select the right intent while receiving a low word score, which is useful
    evidence when deciding whether audio processing helped recognition.
    """
    if not heard.strip():
        return None
    # Offline ASR may spell a contraction as one token or as its full two
    # words. Those are the same acoustic phrase, not evidence that one PCM
    # path recognized speech better. Keep semantic paraphrases distinct here:
    # intent selection is measured separately from transcription quality.
    expansions = {
        "what's": ("what", "is"), "whats": ("what", "is"),
        "who's": ("who", "is"), "where's": ("where", "is"),
        "when's": ("when", "is"), "how's": ("how", "is"),
        "it's": ("it", "is"), "that's": ("that", "is"),
        "i'm": ("i", "am"), "you're": ("you", "are"),
        "we're": ("we", "are"), "they're": ("they", "are"),
    }
    def tokens(text: str) -> list[str]:
        words = re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", text.casefold().replace('’', "'"))
        return [part for word in words for part in expansions.get(word, (word,))][:32]

    reference, decoded = tokens(expected), tokens(heard)
    if not reference or not decoded:
        return None
    previous = list(range(len(decoded) + 1))
    for index, word in enumerate(reference, 1):
        row = [index]
        for column, candidate in enumerate(decoded, 1):
            row.append(min(row[-1] + 1, previous[column] + 1,
                           previous[column - 1] + (word != candidate)))
        previous = row
    return round(max(0.0, 1 - previous[-1] / max(len(reference), len(decoded))), 2)


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
        self.last_raw_heard = ""
        self.last_free_available = False
        self.last_constrained = ""
        self.last_heard_at = 0.0
        self.last_wake_detected = False
        self.last_expected_wake = True
        self.last_intent = ""
        self.last_selection = ""
        self.last_free_wake_detected = False
        self.last_word_match: float | None = None
        self.last_free_text = ''
        self.last_phrase_index = -1
        self.last_confirmed_attempt = -1
        self.correction_examples: dict[str, list[str]] = {}
        self.last_correction_count = 0
        self.applied_gain: int | None = None
        self.gain_adjustments = 0
        self.room_floors: list[float] = []
        self.room_low_fractions: list[float] = []
        self.audio_profile: dict | None = None
        self.trial_profile: AudioProfile | None = None
        self.ambient_until = 0.0
        self.ambient_duration = 0.0
        self.ambient_pending = False
        self.phrase_prompt_at = 0.0

    def processing_regressed(self) -> bool:
        """Compare words and wake evidence, never learned intent, before saving.

        A personalized phrase correction must never make tuned PCM look
        acoustically superior to an untouched recording of the same speech.
        """
        raw_wins = tuned_wins = 0
        for row in self.results:
            if not row.get('raw_compared'):
                continue
            tuned_words = row.get('word_match') or 0
            raw_words = row.get('raw_word_match') or 0
            raw_better = raw_words >= tuned_words + .12
            tuned_better = tuned_words >= raw_words + .12
            raw_wake = row.get('raw_constrained_wake')
            tuned_wake = row.get('constrained_wake_near_start')
            if raw_wake is not None:
                if row['phrase_index'] < len(PHRASES) - 2:
                    raw_better |= bool(raw_wake and not tuned_wake)
                    tuned_better |= bool(tuned_wake and not raw_wake)
                elif tuned_wake and not raw_wake:
                    # New false wake on a no-wake control is enough to veto
                    # amplification; it must never be saved as a "good" tune.
                    return True
                elif raw_wake and not tuned_wake:
                    tuned_better = True
            raw_wins += raw_better and not tuned_better
            tuned_wins += tuned_better and not raw_better
        return raw_wins >= tuned_wins + 2

    def measured_profile(self) -> AudioProfile:
        measured = derive_profile(self.room_floors, self.results,
                                  room_low_fractions=self.room_low_fractions)
        if self.processing_regressed():
            return AudioProfile(1, False, measured.noise_rms,
                                measured.speech_rms, measured.snr_db, 'bypass',
                                measured.low_frequency_noise_fraction)
        # The raw/tuned decoder comparison must evaluate one stable filter.
        # Measurements may continue to update the displayed SNR, but cannot
        # silently change the candidate half-way through the phrase check.
        # A newly unsafe signal still vetoes the frozen choice immediately.
        if measured.quality not in {'clear', 'quiet'} or self.trial_profile is None:
            return measured
        trial = self.trial_profile
        return AudioProfile(trial.gain, trial.high_pass, measured.noise_rms,
                            measured.speech_rms, measured.snr_db, trial.quality,
                            measured.low_frequency_noise_fraction)

    def paired_audio_evidence(self) -> tuple[int, int]:
        """Distinct paired utterances with pre-intent words and wake evidence.

        A post-ASR personal correction may make an intent match even though
        the underlying words were poorly heard. It cannot validate PCM tuning.
        """
        positive = {row['phrase_index'] for row in self.results
                    if row.get('raw_compared') and row.get('matched') and row.get('level_ok')
                    and row.get('lexical_evidence') and row.get('free_wake')
                    and row.get('constrained_wake_near_start')
                    and row.get('raw_constrained_wake') is not None
                    and row['phrase_index'] < len(PHRASES) - 2}
        negative = {row['phrase_index'] for row in self.results
                    if row.get('raw_compared') and row.get('matched') and row.get('level_ok')
                    and row.get('lexical_evidence') and not row.get('free_wake')
                    and not row.get('constrained_wake_near_start')
                    and row.get('raw_constrained_wake') is not None
                    and row['phrase_index'] >= len(PHRASES) - 2}
        return len(positive), len(negative)

    def start(self, now: float | None = None, *, ambient_seconds: float = 0) -> dict:
        now = time.monotonic() if now is None else now
        if not 0 <= ambient_seconds <= 10:
            raise ValueError("Invalid room-noise interval")
        self.session = uuid.uuid4().hex
        # Ten prompts plus two confirmations of a repeatable mishearing can
        # take longer than five minutes at a normal, unhurried pace.
        self.until = now + 900
        # The clock starts with the first *actual* microphone level report,
        # not the UI tap. A slow service startup must not skip the baseline.
        self.ambient_duration = ambient_seconds
        self.ambient_until = 0.0
        self.ambient_pending = ambient_seconds > 0
        self.phrase_prompt_at = 0.0 if self.ambient_pending else now
        self.index = self.attempts = 0
        self.results = []
        self.signal_rms = self.signal_peak = self.signal_at = 0.0
        self.last_heard = ""
        self.last_raw_heard = ""
        self.last_free_available = False
        self.last_constrained = ""
        self.last_heard_at = 0.0
        self.last_wake_detected = False
        self.last_expected_wake = True
        self.last_intent = ""
        self.last_selection = ""
        self.last_free_wake_detected = False
        self.last_word_match = None
        self.last_free_text = ''
        self.last_phrase_index = -1
        self.last_confirmed_attempt = -1
        self.correction_examples.clear()
        self.last_correction_count = 0
        self.applied_gain = None
        self.gain_adjustments = 0
        self.room_floors = []
        self.room_low_fractions = []
        self.audio_profile = None
        self.trial_profile = None
        self.message = ("Stay quiet while Luma measures room sound."
                        if ambient_seconds else "Wait for the microphone to start, then say the phrase.")
        return self.status(now)

    def status(self, now: float | None = None) -> dict:
        now = time.monotonic() if now is None else now
        active = self.until > now and self.index < len(PHRASES) and self.attempts < 32
        ambient_remaining = (math.ceil(self.ambient_duration) if self.ambient_pending
                             else max(0, math.ceil(self.ambient_until - now))) if active else 0
        recent = active and now - self.last_heard_at <= 15
        noise = room_noise_level(self.room_floors)
        regressed = self.processing_regressed()
        independent_positive = {row['phrase_index'] for row in self.results
                                if row['phrase_index'] < len(PHRASES) - 2
                                and row['matched'] and row.get('free_wake')
                                and row.get('constrained_wake_near_start')}
        negative_checks = sum(bool(row['phrase_index'] >= len(PHRASES) - 2
                                   and row.get('acoustic_speech')
                                   and not row.get('free_wake')) for row in self.results)
        paired_positive, paired_negative = self.paired_audio_evidence()
        heard_command = command_after_wake(self.last_free_text)
        correction_available = bool(
            active and recent and self.results
            and self.last_phrase_index == self.index and self.attempts != self.last_confirmed_attempt
            and self.last_wake_detected and self.last_free_wake_detected and heard_command
            and self.results[-1].get('constrained_wake_near_start')
            and normalized_phrase(heard_command)
            and PHRASES[self.index].removeprefix('hey luma ') in LEARNABLE
            and not conflicts_with_existing_command(
                heard_command, PHRASES[self.index].removeprefix('hey luma '))
            and self.results[-1]['acoustic_speech'] and self.results[-1]['level_ok']
            and not self.results[-1]['matched']
        )
        candidate = (self.measured_profile().public()
                     if active and not ambient_remaining and len(self.room_floors) >= 3
                     and sum(bool(item.get('acoustic_speech')) for item in self.results) >= 3
                     else None)
        message = self.message
        if (active and not ambient_remaining and self.signal_at > 0
                and now - self.signal_at <= 3 and self.phrase_prompt_at > 0
                and now - self.phrase_prompt_at >= 12):
            if self.signal_peak <= .0001 and self.signal_rms <= .0001:
                message = ("The microphone stream contains all-zero audio. If you have been speaking, "
                           "check the selected ReSpeaker/PipeWire source or mute state; raising gain will not help.")
            elif self.ambient_duration and not self.room_floors:
                message = "Room sound was not measured. Restart the voice check before changing gain."
            elif self.signal_peak >= .995:
                message = "The microphone is clipping before a phrase completes. Lower capture gain and try again."
            elif self.signal_rms < .002:
                message = ("No speech has risen above the room sound yet. Check the ReSpeaker connection, "
                           "move closer, or adjust capture gain; then say the phrase and pause.")
            else:
                message = ("I see microphone activity but no complete phrase. Say the displayed words "
                           "at normal distance, then pause for a second.")
        return {
            "session": self.session, "active": active,
            "passed": self.index == len(PHRASES),
            "phrase": PHRASES[self.index] if active and not ambient_remaining else None,
            "ambient_remaining": ambient_remaining,
            "expects_wake": PHRASES[self.index].startswith("hey luma ")
            if active and not ambient_remaining else None,
            "completed": self.index, "total": len(PHRASES), "attempts": self.attempts,
            "message": (("Stay quiet while Luma measures room sound."
                         if ambient_remaining else message)
                        if active or self.index == len(PHRASES)
                        else "Start a new check when you are ready."),
            "signal_available": active and self.signal_at > 0 and now - self.signal_at <= 3,
            "signal_rms": self.signal_rms, "signal_peak": self.signal_peak,
            "last_heard": self.last_heard if recent else "",
            "last_raw_heard": self.last_raw_heard if recent else "",
            "last_free_available": self.last_free_available if recent else False,
            "last_constrained": self.last_constrained if recent else "",
            "last_wake_detected": self.last_wake_detected if recent else None,
            "last_free_wake_detected": self.last_free_wake_detected if recent else None,
            "last_word_match": self.last_word_match if recent else None,
            "last_expected_wake": self.last_expected_wake if recent else None,
            "last_intent": self.last_intent if recent else "",
            "last_selection": self.last_selection if recent else "",
            "applied_gain": self.applied_gain,
            "gain_adjustments": self.gain_adjustments,
            "room_noise_rms": round(noise, 5) if noise is not None else None,
            "room_low_frequency_fraction": (round(median(self.room_low_fractions), 2)
                                            if len(self.room_low_fractions) >= 3 else None),
            "audio_profile": self.audio_profile,
            "audio_candidate": candidate,
            "processing_regressed": regressed,
            "paired_positive_checks": paired_positive,
            "paired_negative_checks": paired_negative,
            "audio_trial_ready": paired_positive >= 2 and paired_negative >= 1,
            "independent_wakes": len(independent_positive),
            "negative_wake_checks": negative_checks,
            "strict_wake_ready": len(independent_positive) >= 4 and negative_checks >= 1,
            "correction_available": correction_available,
            "correction_confirmations": self.last_correction_count,
            "results": list(self.results),
        }

    def confirm_correction(self, session: str, now: float | None = None) -> tuple[list[str], str, int]:
        """Owner confirms two attempts, allowing natural ASR variation."""
        now = time.monotonic() if now is None else now
        if session != self.session or not self.status(now)['correction_available']:
            raise ValueError('No recent, safe phrase correction is ready to confirm.')
        heard = normalized_phrase(command_after_wake(self.last_free_text) or '')
        canonical = PHRASES[self.index].removeprefix('hey luma ')
        self.last_confirmed_attempt = self.attempts
        examples = self.correction_examples.setdefault(canonical, [])
        if len(examples) < 2:
            examples.append(heard)
        self.last_correction_count = len(examples)
        self.message = ('Confirmed. Say the displayed phrase once more; a different mishearing is okay.'
                        if self.last_correction_count < 2 else
                        'Two examples confirmed. Repeat the displayed phrase to test it.')
        return list(dict.fromkeys(examples)), canonical, self.last_correction_count

    def gain_step(self, rms: float, peak: float, clipped_fraction: float = 0) -> int:
        """Adjust only obvious level faults; never chase a recognition mismatch.

        A near-zero peak usually means an absent capture route, not low gain.
        Limit the entire session to three reversible four-step hardware moves.
        """
        if self.gain_adjustments >= 3:
            return 0
        if peak >= .995 or clipped_fraction > .002:
            return -4
        if CALIBRATION_MIN_PEAK <= peak < .5 and rms < .002:
            if self.room_floors:
                floor = sorted(self.room_floors)[len(self.room_floors) // 2]
                if floor >= rms / 3:
                    return 0  # Amplifying this input would mostly raise noise.
            return 4
        return 0

    def record_gain(self, gain: int) -> None:
        self.applied_gain = gain
        self.gain_adjustments += 1
        # Raw noise and speech measurements from different hardware gains are
        # not comparable. Start a fresh room baseline and phrase check while
        # preserving the three-adjustment safety limit for this session.
        self.index = self.attempts = 0
        self.results.clear()
        self.room_floors.clear()
        self.room_low_fractions.clear()
        self.audio_profile = None
        self.trial_profile = None
        self.ambient_until = 0.0
        self.ambient_pending = self.ambient_duration > 0
        self.phrase_prompt_at = 0.0
        self.signal_rms = self.signal_peak = self.signal_at = 0.0
        self.last_heard = self.last_constrained = self.last_intent = self.last_selection = ""
        self.last_free_wake_detected = False
        self.last_word_match = None
        self.last_free_text = ''
        self.last_phrase_index = -1
        self.last_confirmed_attempt = -1
        self.correction_examples.clear()
        self.last_correction_count = 0
        self.last_raw_heard = ""
        self.last_free_available = False
        self.last_heard_at = 0.0
        self.message = (f"Capture gain adjusted to {gain} of 63. Stay quiet for a new room baseline, "
                        "then repeat the phrase check." if self.ambient_pending else
                        f"Capture gain adjusted to {gain} of 63; repeat the phrase check.")

    def report_level(self, session: str, rms: float, peak: float, now: float | None = None,
                     *, floor_rms: float | None = None,
                     floor_low_frequency_fraction: float | None = None) -> dict:
        """Keep only short-lived numeric level data while the owner is calibrating."""
        now = time.monotonic() if now is None else now
        if session != self.session or not self.status(now)["active"]:
            raise ValueError("Calibration session has expired")
        if not (0 <= rms <= 1 and 0 <= peak <= 1
                and (floor_rms is None or 0 <= floor_rms <= 1)
                and (floor_low_frequency_fraction is None
                     or 0 <= floor_low_frequency_fraction <= 1)):
            raise ValueError("Invalid microphone level")
        if self.ambient_pending:
            self.ambient_until = now + self.ambient_duration
            self.ambient_pending = False
            self.phrase_prompt_at = self.ambient_until
        self.signal_rms = round(rms, 4)
        self.signal_peak = round(peak, 4)
        self.signal_at = now
        if floor_rms is not None and (self.ambient_until == 0 or now <= self.ambient_until):
            self.room_floors.append(floor_rms)
            self.room_floors = self.room_floors[-300:]
            if floor_low_frequency_fraction is not None:
                self.room_low_fractions.append(floor_low_frequency_fraction)
                self.room_low_fractions = self.room_low_fractions[-300:]
        return self.status(now)

    def submit(self, session: str, text: str, rms: float, peak: float, now: float | None = None,
               *, free_text: str = "", raw_free_text: str = "", raw_compared: bool = False,
               raw_constrained_wake: bool | None = None,
               selected_text: str | None = None,
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
        if raw_constrained_wake is not None and (type(raw_constrained_wake) is not bool
                                                 or not raw_compared):
            raise ValueError("Invalid raw wake comparison")
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
        raw_match = False
        if raw_compared:
            raw_wake = WakeGate().accept(raw_free_text, now)
            raw_command = parse_local_command((raw_wake if expects_wake else raw_free_text) or '')
            raw_match = bool(raw_command and expected and
                             (raw_constrained_wake is None
                              or raw_constrained_wake == expects_wake) and
                             (raw_wake is not None) == expects_wake and
                             (raw_command.name, raw_command.value) == (expected.name, expected.value))
        noise = room_noise_level(self.room_floors) or 0.0
        acoustic_speech = (rms >= max(CALIBRATION_MIN_RMS, noise * 2.5)
                           and peak >= max(CALIBRATION_MIN_PEAK, noise * 4))
        level_ok = .002 <= rms and peak < .995 and clipped_fraction <= .002
        self.attempts += 1
        self.phrase_prompt_at = now
        # Only the live local setup page can see this short-lived transcript.
        # Persistent results retain numeric levels and matches, never speech.
        self.last_heard = (free_text or text)[:160]
        self.last_raw_heard = raw_free_text[:160] if raw_compared else ""
        self.last_free_available = bool(free_text)
        self.last_constrained = text[:160] if free_text else ""
        self.last_heard_at = now
        self.last_wake_detected = accepted is not None
        self.last_expected_wake = expects_wake
        self.last_selection = selection
        self.last_free_wake_detected = wake_near_start(free_text)
        self.last_word_match = word_match_fraction(PHRASES[self.index], free_text)
        lexical_evidence = (selection != 'learned' and self.last_word_match is not None
                            and self.last_word_match >= .75)
        raw_word_match = (word_match_fraction(PHRASES[self.index], raw_free_text)
                          if raw_compared else None)
        self.last_free_text = free_text[:160]
        self.last_phrase_index = self.index
        canonical = PHRASES[self.index].removeprefix('hey luma ')
        self.last_correction_count = len(self.correction_examples.get(canonical, []))
        if command:
            value = getattr(command.value, "value", command.value)
            self.last_intent = (f"{command.name.value}: {value}" if value is not None
                                else command.name.value)
        else:
            self.last_intent = ""
        # Aggregate levels/results only, never transcripts or audio samples.
        self.results.append({"phrase_index": self.index, "matched": matched,
                             "free_wake": self.last_free_wake_detected,
                             "constrained_wake_near_start": wake_near_start(text),
                             "word_match": self.last_word_match,
                             "lexical_evidence": lexical_evidence,
                             "raw_word_match": raw_word_match,
                             "raw_compared": raw_compared, "raw_match": raw_match,
                             "raw_constrained_wake": raw_constrained_wake,
                             "level_ok": level_ok,
                             "acoustic_speech": acoustic_speech,
                             "rms": round(rms, 5), "peak": round(peak, 5),
                             "dc": round(dc, 5),
                             "clipped_fraction": round(clipped_fraction, 5)})
        if (self.trial_profile is None and len(self.room_floors) >= 3
                and sum(bool(item.get('acoustic_speech')) for item in self.results) >= 3):
            proposed = derive_profile(self.room_floors, self.results,
                                      room_low_fractions=self.room_low_fractions)
            if proposed.quality in {'clear', 'quiet'}:
                self.trial_profile = proposed
        if matched and level_ok:
            self.index += 1
            self.message = "All voice checks passed. Try again if the room or microphone placement changes." if self.index == len(PHRASES) else "That worked. Say the next phrase."
            if self.index == len(PHRASES):
                self.last_heard = ""
                proposed = self.measured_profile()
                positive_checks, negative_checks = self.paired_audio_evidence()
                auto_tune_unverified = ((proposed.gain > 1 or proposed.high_pass)
                                        and (positive_checks < 2 or negative_checks < 1))
                if auto_tune_unverified:
                    # Passing the phrases on mostly untouched PCM does not
                    # prove that the trial filter is safe to auto-save. The
                    # owner can still make a separate, explicit early save.
                    proposed = AudioProfile(1, False, proposed.noise_rms,
                                            proposed.speech_rms, proposed.snr_db,
                                            'bypass', proposed.low_frequency_noise_fraction)
                    self.message = ("Phrase checks passed, but trial audio lacked two paired command phrases "
                                    "and one paired no-wake phrase. Processing was not saved; the mic stays untouched.")
                self.audio_profile = proposed.public()
                if self.audio_profile['quality'] == 'noisy':
                    self.message += " Room noise is high; Luma left the audio untouched. Recheck placement before relying on voice."
                elif self.audio_profile['quality'] == 'clipped':
                    self.message += " Some speech clipped; lower ReSpeaker capture gain and repeat."
                elif self.audio_profile['quality'] == 'unstable':
                    self.message += " Room sound changed sharply during measurement; audio remains untouched. Repeat the quiet-room check."
                elif self.audio_profile['quality'] == 'bypass' and not auto_tune_unverified:
                    self.message += (" Untouched audio recognized words or wakes better, so processing stays off."
                                     if self.processing_regressed() else
                                     " Room sound was not measured well enough to tune processing; audio remains untouched.")
        elif self.processing_regressed():
            self.message = "Untouched audio handled words or wake detection better; trial processing is off. Repeat the displayed phrase."
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
        self.index = self.attempts = 0
        self.results.clear()
        self.room_floors.clear()
        self.room_low_fractions.clear()
        self.audio_profile = None
        self.trial_profile = None
        self.phrase_prompt_at = 0.0
        self.last_heard = ""
        self.last_raw_heard = ""
        self.last_free_available = False
        self.last_constrained = ""
        self.last_wake_detected = False
        self.last_expected_wake = True
        self.last_intent = ""
        self.last_selection = ""
        self.last_free_wake_detected = False
        self.last_word_match = None
        self.last_free_text = ''
        self.last_phrase_index = -1
        self.last_confirmed_attempt = -1
        self.correction_examples.clear()
        self.last_correction_count = 0
