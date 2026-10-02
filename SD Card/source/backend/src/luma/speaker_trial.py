"""Consent-driven, ephemeral speaker-separation experiment.

This is deliberately not an authorization service. It keeps vectors only in
RAM while the owner collects independent holdouts, then retains aggregate
scores only. In particular, starting or passing a trial never changes voice
command gating or the phone/PIN privacy boundary.
"""
from __future__ import annotations

import math
import time
import uuid
from statistics import median

from .voice_speaker import (SpeakerObservation, SpeakerVectorError,
                            assess_speaker_trial, speaker_similarity)


STEPS = (
    ('enrollment', 'Say a full sentence in your normal voice for about six seconds.'),
    ('enrollment', 'Say a different full sentence from your usual distance.'),
    ('enrollment', 'Say another sentence, a little softer or from farther away.'),
    ('owner_holdout', 'Say a new sentence; this one is held out from enrollment.'),
    ('owner_holdout', 'Say one more new sentence in your ordinary speaking voice.'),
    ('nonowner_holdout', 'Play another person or Zoom voice for about six seconds. Do not speak yourself.'),
    ('nonowner_holdout', 'Play a second independent sample of another voice.'),
    ('nonowner_holdout', 'Play a third independent sample of another voice.'),
)
MAX_TRIAL_SECONDS = 900
MAX_ARM_SECONDS = 45
MAX_RECORD_SECONDS = 30
ERRORS = frozenset({'capture_gap', 'capture_stopped', 'model_unavailable',
                    'speech_too_short', 'too_quiet', 'clipped', 'decode_failed'})


class SpeakerTrial:
    def __init__(self):
        self.session = ''
        self.until = 0.0
        self.phase = 'idle'
        self.index = 0
        self.token = ''
        self.record_deadline = 0.0
        self.last_error: str | None = None
        self.report: dict | None = None
        self._samples: dict[str, list[SpeakerObservation]] = {
            'enrollment': [], 'owner_holdout': [], 'nonowner_holdout': []}
        self._decode_ms: list[float] = []
        self._model_load_ms: float | None = None
        self._peak_rss_kib: int | None = None

    def _drop_samples(self) -> None:
        self._samples = {'enrollment': [], 'owner_holdout': [], 'nonowner_holdout': []}

    def _drop_metrics(self) -> None:
        self._decode_ms.clear()
        self._model_load_ms = None
        self._peak_rss_kib = None

    def _expire(self, now: float) -> None:
        if self.phase in {'ready', 'arming', 'recording'} and now >= self.until:
            self.cancel(expired=True)
        elif self.phase == 'arming' and now >= self.record_deadline:
            self.phase, self.token, self.last_error = 'ready', '', 'capture_stopped'
        elif self.phase == 'recording' and now >= self.record_deadline:
            self.phase, self.token, self.last_error = 'ready', '', 'capture_stopped'

    def status(self, now: float | None = None) -> dict:
        now = time.monotonic() if now is None else now
        self._expire(now)
        current = STEPS[self.index] if self.phase in {'ready', 'arming', 'recording'} else None
        return {'session': self.session, 'active': self.phase in {'ready', 'arming', 'recording'},
                'phase': self.phase, 'completed': self.index, 'total': len(STEPS),
                'role': current[0] if current else None,
                'prompt': current[1] if current else None,
                'token': self.token if self.phase in {'arming', 'recording'} else None,
                'remaining_seconds': max(0, int(self.until - now)) if current else 0,
                'last_error': self.last_error, 'report': self.report}

    def start(self, now: float | None = None) -> dict:
        now = time.monotonic() if now is None else now
        self._expire(now)
        if self.phase in {'ready', 'arming', 'recording'}:
            raise SpeakerVectorError('A speaker trial is already active.')
        self.session = uuid.uuid4().hex
        self.until = now + MAX_TRIAL_SECONDS
        self.phase = 'ready'
        self.index = 0
        self.token = ''
        self.record_deadline = 0.0
        self.last_error = None
        self.report = None
        self._drop_samples()
        self._drop_metrics()
        return self.status(now)

    def begin(self, session: str, now: float | None = None) -> dict:
        now = time.monotonic() if now is None else now
        self._expire(now)
        if session != self.session or self.phase != 'ready':
            raise SpeakerVectorError('No speaker sample is ready to start.')
        self.phase = 'arming'
        self.token = uuid.uuid4().hex
        self.record_deadline = min(self.until, now + MAX_ARM_SECONDS)
        self.last_error = None
        return self.status(now)

    def armed(self, session: str, token: str, now: float | None = None) -> dict:
        now = time.monotonic() if now is None else now
        self._expire(now)
        if session != self.session or token != self.token or self.phase != 'arming':
            raise SpeakerVectorError('That speaker sample is no longer armed.')
        self.phase = 'recording'
        self.record_deadline = min(self.until, now + MAX_RECORD_SECONDS)
        return self.status(now)

    def submit(self, session: str, token: str, *, vector: list[float] | None = None,
               spk_frames: int | None = None, input_seconds: float | None = None,
               model_load_ms: float | None = None, decode_ms: float | None = None,
               rss_kib: int | None = None,
               error: str | None = None, now: float | None = None) -> dict:
        now = time.monotonic() if now is None else now
        self._expire(now)
        if session != self.session or token != self.token or self.phase != 'recording':
            raise SpeakerVectorError('That speaker sample is no longer being recorded.')
        if error is not None:
            if error not in ERRORS or vector is not None:
                raise SpeakerVectorError('Invalid speaker sample result.')
            self.phase, self.token, self.last_error = 'ready', '', error
            return self.status(now)
        if ((model_load_ms is not None and
             (type(model_load_ms) not in (int, float) or not math.isfinite(model_load_ms)
              or not 0 <= model_load_ms <= 60_000))
                or (decode_ms is not None and
                    (type(decode_ms) not in (int, float) or not math.isfinite(decode_ms)
                     or not 0 <= decode_ms <= 60_000))
                or (rss_kib is not None and
                    (type(rss_kib) is not int or not 0 < rss_kib <= 8_388_608))):
            raise SpeakerVectorError('Invalid speaker performance measurements.')
        if (not isinstance(vector, list) or not 64 <= len(vector) <= 512
                or type(spk_frames) is not int or not 1 <= spk_frames <= 3000
                or type(input_seconds) not in (int, float)
                or not math.isfinite(input_seconds) or not 4 <= input_seconds <= 8
                or any(type(value) not in (int, float) or not math.isfinite(value)
                       or abs(value) > 2 for value in vector)):
            raise SpeakerVectorError('Invalid speaker sample result.')
        observation = SpeakerObservation(tuple(float(value) for value in vector),
                                         spk_frames, float(input_seconds))
        # Validate a nonzero vector and matching dimensions before committing
        # it. Duplicated vectors cannot stand in for independent recordings.
        speaker_similarity(observation, observation)
        previous = [sample for group in self._samples.values() for sample in group]
        if any(sample.vector == observation.vector for sample in previous) or (
                previous and len(previous[0].vector) != len(observation.vector)):
            raise SpeakerVectorError('Speaker samples must be independent and compatible.')
        role, _prompt = STEPS[self.index]
        self._samples[role].append(observation)
        if decode_ms is not None:
            self._decode_ms.append(float(decode_ms))
        if self._model_load_ms is None and model_load_ms is not None and model_load_ms > 0:
            self._model_load_ms = float(model_load_ms)
        if rss_kib is not None:
            self._peak_rss_kib = max(self._peak_rss_kib or 0, rss_kib)
        self.index += 1
        self.token = ''
        self.last_error = None
        if self.index < len(STEPS):
            self.phase = 'ready'
            return self.status(now)
        try:
            result = assess_speaker_trial(self._samples['enrollment'],
                                          self._samples['owner_holdout'],
                                          self._samples['nonowner_holdout'])
        except SpeakerVectorError:
            self.phase = 'failed'
            self.last_error = 'assessment_failed'
            self._drop_metrics()
            raise
        finally:
            self._drop_samples()
        self.phase = 'complete'
        self.report = {'observed_separation': result.observed_separation,
                       'enrollment_floor': round(result.enrollment_floor, 3),
                       'owner_holdout_floor': round(result.owner_holdout_floor, 3),
                       'nonowner_holdout_ceiling': round(result.nonowner_holdout_ceiling, 3),
                       'candidate_threshold': (round(result.candidate_threshold, 3)
                                               if result.candidate_threshold is not None else None),
                       'model_load_ms': (round(self._model_load_ms) if self._model_load_ms is not None else None),
                       'median_decode_ms': (round(median(self._decode_ms)) if self._decode_ms else None),
                       'voice_process_peak_rss_mb': (round(self._peak_rss_kib / 1024, 1)
                                                     if self._peak_rss_kib is not None else None)}
        self._drop_metrics()
        return self.status(now)

    def cancel(self, *, expired: bool = False) -> dict:
        self.phase = 'expired' if expired else 'cancelled'
        self.token = ''
        self.record_deadline = 0.0
        self.last_error = None
        self.report = None
        self._drop_samples()
        self._drop_metrics()
        return self.status()
