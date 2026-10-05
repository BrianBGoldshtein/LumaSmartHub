"""Bounded acoustic position guard; never authorizes commands itself.

Leading quiet audio must not disqualify a genuine wake, but a compact keyword
deep inside ordinary speech must not open a listening window. Measure the
first sustained energy onset, then allow a short natural lead-in. This is not
speaker identity or a neural VAD; owner/noisy-room acceptance remains required.
"""
from array import array
import math
import sys

from .keyword_wake import KeywordEvidence, KeywordWakeError, RATE, validate_audio

MAX_WAKE_LEAD_SECONDS = 1.2
ONSET_TOLERANCE_SECONDS = .25


def first_sustained_sound(frames, *, noise_rms=0.0):
    validate_audio(frames)
    if (type(noise_rms) not in (int, float) or not math.isfinite(noise_rms)
            or not 0 <= noise_rms <= 1):
        raise KeywordWakeError('keyword_noise_invalid')
    pcm = array('h', b''.join(frames))
    if sys.byteorder != 'little':
        pcm.byteswap()
    window = RATE//50  # 20ms; do not confuse leading silence with speech.
    consecutive = 0
    for offset in range(0,len(pcm),window):
        section = pcm[offset:offset+window]
        if len(section) < window:
            break
        rms = math.sqrt(sum(value*value for value in section)/window)/32768
        peak = max(abs(value) for value in section)/32768
        loud = rms >= max(.001, noise_rms*2.5) and peak >= max(.003, noise_rms*4)
        consecutive = consecutive+1 if loud else 0
        if consecutive == 2:
            return (offset-window)/RATE
    return None


def keyword_near_sound_start(evidence: KeywordEvidence, frames, *, noise_rms=0.0):
    start = first_sustained_sound(frames, noise_rms=noise_rms)
    timestamp = evidence.first_token_seconds
    if not evidence.detected or start is None or timestamp is None:
        return False
    if (type(timestamp) not in (int,float) or not math.isfinite(timestamp)
            or timestamp < 0 or timestamp > validate_audio(frames)+1):
        raise KeywordWakeError('keyword_result_invalid')
    return -ONSET_TOLERANCE_SECONDS <= timestamp-start <= MAX_WAKE_LEAD_SECONDS
