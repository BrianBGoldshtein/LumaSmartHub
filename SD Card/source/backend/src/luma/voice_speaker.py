"""Offline speaker-vector qualification, not an authentication mechanism.

Vosk's optional speaker model emits an x-vector with ``spk_frames``. A short
"Hey Luma" alone is insufficient evidence for an owner gate. This module
accepts bounded, longer recordings for a future explicit enrollment trial;
it neither loads a model nor stores any biometric profile by itself.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any

from .voice_signal import pcm_measurements


RATE = 16_000
MIN_SAMPLE_SECONDS = 4.0
MAX_SAMPLE_SECONDS = 8.0
MIN_VOICED_SECONDS = 3.0
MIN_VECTOR_DIM = 64
MAX_VECTOR_DIM = 512


class SpeakerVectorError(ValueError):
    """A sample cannot be used for an owner-voice trial."""


@dataclass(frozen=True)
class SpeakerObservation:
    vector: tuple[float, ...]
    spk_frames: int
    input_seconds: float


def _observation(result: Any, seconds: float) -> SpeakerObservation | None:
    if not isinstance(result, dict):
        return None
    values = result.get('spk')
    frames = result.get('spk_frames')
    if (not isinstance(values, list) or not MIN_VECTOR_DIM <= len(values) <= MAX_VECTOR_DIM
            or type(frames) is not int or frames <= 0):
        return None
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
        return None
    norm = math.sqrt(sum(value * value for value in values))
    if not math.isfinite(norm) or norm < 1e-6:
        return None
    return SpeakerObservation(tuple(value / norm for value in values), frames, seconds)


def decode_speaker_observation(recognizer: Any, pcm_frames: list[bytes],
                               *, noise_rms: float = 0.0) -> SpeakerObservation:
    """Replay one bounded 16 kHz utterance through a speaker-enabled Vosk recognizer.

    Caller must attach ``SpkModel`` before recognition begins. ``spk_frames``
    is retained because Vosk may endpoint several times; choose its longest
    *reported* vector, not simply the last final segment. No words are kept.
    """
    if not pcm_frames or len(pcm_frames) > 32 or any(
            not isinstance(frame, bytes) or not frame or len(frame) % 2
            for frame in pcm_frames):
        raise SpeakerVectorError('Invalid speaker-trial PCM.')
    seconds = sum(len(frame) for frame in pcm_frames) / (RATE * 2)
    if not MIN_SAMPLE_SECONDS <= seconds <= MAX_SAMPLE_SECONDS:
        raise SpeakerVectorError('Speaker trials need four to eight seconds of speech.')
    if not math.isfinite(noise_rms) or not 0 <= noise_rms <= .1:
        raise SpeakerVectorError('Invalid speaker-trial room level.')
    levels = [pcm_measurements(frame) for frame in pcm_frames]
    if any(level['peak'] >= .995 or level['clipped_fraction'] > .002 for level in levels):
        raise SpeakerVectorError('The speaker sample clipped before recognition.')
    voiced_seconds = sum(
        len(frame) / (RATE * 2) for frame, level in zip(pcm_frames, levels)
        if level['rms'] >= max(.0008, noise_rms * 2.5)
        and level['peak'] >= max(.005, noise_rms * 4)
    )
    if voiced_seconds < MIN_VOICED_SECONDS:
        raise SpeakerVectorError('Too little speech rose above the room sound.')
    try:
        recognizer.Reset()
        results = []
        for frame in pcm_frames:
            if recognizer.AcceptWaveform(frame):
                results.append(json.loads(recognizer.Result()))
        results.append(json.loads(recognizer.FinalResult()))
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        raise SpeakerVectorError('The speaker model did not decode this sample.') from None
    vectors = [item for result in results
               if (item := _observation(result, seconds)) is not None]
    if not vectors:
        raise SpeakerVectorError('No usable speaker vector was produced.')
    return max(vectors, key=lambda item: item.spk_frames)


def speaker_similarity(left: SpeakerObservation, right: SpeakerObservation) -> float:
    """Cosine similarity; higher is closer, but no universal threshold exists."""
    if len(left.vector) != len(right.vector) or not left.vector:
        raise SpeakerVectorError('Speaker vector dimensions do not match.')
    if any(not math.isfinite(value) for value in (*left.vector, *right.vector)):
        raise SpeakerVectorError('Speaker vector contains invalid values.')
    norm_left = math.sqrt(sum(value * value for value in left.vector))
    norm_right = math.sqrt(sum(value * value for value in right.vector))
    if not math.isfinite(norm_left * norm_right) or norm_left < 1e-6 or norm_right < 1e-6:
        raise SpeakerVectorError('Speaker vector has no usable magnitude.')
    score = sum(a * b for a, b in zip(left.vector, right.vector)) / (norm_left * norm_right)
    return max(-1.0, min(1.0, score))
