"""Owner-started, RAM-only false-wake trial for call/TV background speech.

The trial never accepts commands or persists words/audio. Its counters compare
the existing constrained wake with the optional unrestricted near-start check;
they do not identify a speaker or establish a false-accept rate by themselves.
"""
from __future__ import annotations

import math
import time
import uuid


class VoiceCallTrial:
    DURATION_SECONDS = 90
    MAX_HEARTBEAT_GAP_SECONDS = 15

    def __init__(self) -> None:
        self.session = ""
        self.started_at = 0.0
        self.until = 0.0
        self.last_heartbeat_at = 0.0
        self.interrupted = False
        self.utterances = 0
        self.partial_wakes = 0
        self.constrained_wakes = 0
        self.dual_wakes = 0
        self.quoted_wakes = 0
        self.raw_compared_utterances = 0
        self.raw_constrained_wakes = 0
        self.raw_dual_wakes = 0
        self.processed_dual_compared = 0
        self.tuned_only_dual_wakes = 0
        self.raw_only_dual_wakes = 0

    def start(self, now: float | None = None) -> dict:
        now = time.monotonic() if now is None else now
        if self.status(now)["active"]:
            raise ValueError("A call test is already running.")
        self.session = uuid.uuid4().hex
        self.started_at = now
        self.until = now + self.DURATION_SECONDS
        self.last_heartbeat_at = now
        self.interrupted = False
        self.utterances = self.partial_wakes = self.constrained_wakes = 0
        self.dual_wakes = self.quoted_wakes = 0
        self.raw_compared_utterances = self.raw_constrained_wakes = self.raw_dual_wakes = 0
        self.processed_dual_compared = 0
        self.tuned_only_dual_wakes = self.raw_only_dual_wakes = 0
        return self.status(now)

    def stop(self) -> dict:
        self.until = 0.0
        return self.status()

    def heartbeat(self, now: float | None = None) -> None:
        """A running capture service must cover the entire negative trial."""
        now = time.monotonic() if now is None else now
        if not self.session or not self.started_at < now < self.until:
            return
        if now - self.last_heartbeat_at > self.MAX_HEARTBEAT_GAP_SECONDS:
            self.interrupted = True
        self.last_heartbeat_at = now

    def status(self, now: float | None = None) -> dict:
        now = time.monotonic() if now is None else now
        active = bool(self.session and now < self.until)
        return {
            "session": self.session,
            "active": active,
            "remaining_seconds": max(0, math.ceil(self.until - now)) if active else 0,
            # Only a full-length, speech-bearing owner-started trial can
            # supply the negative evidence for an early wake-only check.
            # A stopped/empty trial or one with confirmed wakes cannot.
            "negative_ready": bool(self.session and self.until > self.started_at
                                   and now >= self.until and self.utterances >= 5
                                   and self.dual_wakes == 0 and not self.interrupted
                                   and self.last_heartbeat_at >=
                                   self.until - self.MAX_HEARTBEAT_GAP_SECONDS),
            "interrupted": self.interrupted,
            "utterances": self.utterances,
            "partial_wakes": self.partial_wakes,
            "constrained_wakes": self.constrained_wakes,
            "dual_wakes": self.dual_wakes,
            "quoted_wakes": self.quoted_wakes,
            "raw_compared_utterances": self.raw_compared_utterances,
            "raw_constrained_wakes": self.raw_constrained_wakes,
            "raw_dual_wakes": self.raw_dual_wakes,
            "processed_dual_compared": self.processed_dual_compared,
            "tuned_only_dual_wakes": self.tuned_only_dual_wakes,
            "raw_only_dual_wakes": self.raw_only_dual_wakes,
        }

    def record(self, session: str, *, partial_wake: bool, constrained_wake: bool,
               constrained_near_start: bool, free_wake: bool,
               free_near_start: bool, raw_compared: bool = False,
               raw_constrained_wake: bool | None = None,
               raw_constrained_near_start: bool | None = None,
               raw_free_wake: bool | None = None,
               raw_free_near_start: bool | None = None,
               now: float | None = None) -> dict:
        now = time.monotonic() if now is None else now
        if session != self.session or not self.status(now)["active"]:
            raise ValueError("The call test is not active.")
        if any(type(value) is not bool for value in (
                partial_wake, constrained_wake, constrained_near_start,
                free_wake, free_near_start)):
            raise ValueError("Invalid call-test observation.")
        if (constrained_near_start and not constrained_wake
                or free_near_start and not free_wake
                or free_wake and not constrained_wake):
            raise ValueError("Inconsistent call-test observation.")
        raw_values = (raw_constrained_wake, raw_constrained_near_start,
                      raw_free_wake, raw_free_near_start)
        if type(raw_compared) is not bool or (
                raw_compared and any(type(value) is not bool for value in raw_values)) or (
                not raw_compared and any(value is not None for value in raw_values)):
            raise ValueError('Invalid raw call-test comparison.')
        if raw_compared and (raw_constrained_near_start and not raw_constrained_wake
                             or raw_free_near_start and not raw_free_wake
                             or raw_free_wake and not raw_constrained_wake):
            raise ValueError('Inconsistent raw call-test comparison.')
        self.utterances += 1
        if partial_wake:
            self.partial_wakes += 1
        if constrained_wake:
            self.constrained_wakes += 1
            if constrained_near_start and free_near_start:
                self.dual_wakes += 1
            elif free_wake and not free_near_start:
                self.quoted_wakes += 1
        if raw_compared:
            self.raw_compared_utterances += 1
            self.raw_constrained_wakes += bool(raw_constrained_wake)
            raw_dual = bool(raw_constrained_near_start and raw_free_near_start)
            tuned_dual = bool(constrained_near_start and free_near_start)
            self.raw_dual_wakes += raw_dual
            self.processed_dual_compared += tuned_dual
            self.tuned_only_dual_wakes += tuned_dual and not raw_dual
            self.raw_only_dual_wakes += raw_dual and not tuned_dual
        return self.status(now)
