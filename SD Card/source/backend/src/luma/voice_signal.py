"""Conservative, local PCM conditioning before wake/word recognition.

No recordings or transcripts are persisted. A profile is created only after a
guided hardware check and is bypassed when the room is too noisy or clipped.
"""
from __future__ import annotations

from array import array
from dataclasses import dataclass
import math
from statistics import median
import sys


RATE = 16_000
HIGH_PASS_HZ = 75
HIGH_PASS_ALPHA = math.exp(-2 * math.pi * HIGH_PASS_HZ / RATE)


@dataclass(frozen=True)
class AudioProfile:
    gain: float = 1.0
    high_pass: bool = False
    noise_rms: float = 0.0
    speech_rms: float = 0.0
    snr_db: float | None = None
    quality: str = "unmeasured"
    low_frequency_noise_fraction: float | None = None

    def public(self) -> dict:
        result = {"version": 1, "gain": self.gain, "high_pass": self.high_pass,
                  "noise_rms": round(self.noise_rms, 5),
                  "speech_rms": round(self.speech_rms, 5),
                  "snr_db": None if self.snr_db is None else round(self.snr_db, 1),
                  "quality": self.quality}
        if self.low_frequency_noise_fraction is not None:
            result["low_frequency_noise_fraction"] = round(self.low_frequency_noise_fraction, 2)
        return result


def read_profile(value: object) -> AudioProfile:
    """Reject corrupt/stale configuration instead of amplifying unexpectedly."""
    if not isinstance(value, dict) or value.get("version") != 1:
        return AudioProfile()
    gain = value.get("gain")
    high_pass = value.get("high_pass")
    if (type(gain) not in (int, float) or not math.isfinite(gain)
            or not 1 <= gain <= 2 or type(high_pass) is not bool):
        return AudioProfile()
    noise = value.get("noise_rms", 0.0)
    speech = value.get("speech_rms", 0.0)
    snr = value.get("snr_db")
    if (type(noise) not in (int, float) or not 0 <= noise <= 1
            or type(speech) not in (int, float) or not 0 <= speech <= 1
            or (snr is not None and (type(snr) not in (int, float) or not math.isfinite(snr)
                                     or not -60 <= snr <= 90))):
        return AudioProfile()
    quality = value.get("quality")
    low_fraction = value.get("low_frequency_noise_fraction")
    if low_fraction is not None and (type(low_fraction) not in (int, float)
                                     or not math.isfinite(low_fraction)
                                     or not 0 <= low_fraction <= 1):
        return AudioProfile()
    if quality not in {"clear", "quiet", "noisy", "clipped", "unstable", "bypass"}:
        return AudioProfile()
    if quality in {"noisy", "clipped", "unstable", "bypass"} and (gain != 1 or high_pass):
        return AudioProfile()
    return AudioProfile(float(gain), high_pass, float(noise), float(speech),
                        None if snr is None else float(snr), quality,
                        None if low_fraction is None else float(low_fraction))


def low_frequency_fraction(pcm: bytes) -> float:
    """Fraction of room-noise energy suppressed by the actual 75 Hz filter.

    Only a quiet-room frame is used for profile selection. This is a cheap
    time-domain measurement, not a claim about the speaker's accent or pitch.
    """
    if len(pcm) < 2 or len(pcm) % 2:
        raise ValueError("PCM must contain whole 16-bit samples")
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    previous_input = previous_output = 0.0
    raw_energy = filtered_energy = 0.0
    for sample in samples:
        filtered = HIGH_PASS_ALPHA * (previous_output + sample - previous_input)
        previous_input, previous_output = float(sample), filtered
        raw_energy += sample * sample
        filtered_energy += filtered * filtered
    if raw_energy < len(samples) * 1.0:
        return 0.0  # Digital silence does not establish a frequency profile.
    return max(0.0, min(1.0, 1.0 - filtered_energy / raw_energy))


def pcm_measurements(pcm: bytes) -> dict[str, float]:
    """Measure normalized raw PCM without retaining a waveform."""
    if len(pcm) < 2 or len(pcm) % 2:
        raise ValueError("PCM must contain whole 16-bit samples")
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    count = len(samples)
    total = sum(samples)
    square = sum(value * value for value in samples)
    peak = max(abs(value) for value in samples)
    clipped = sum(abs(value) >= 32440 for value in samples)
    return {"rms": math.sqrt(square / count) / 32768,
            "peak": peak / 32768,
            "dc": abs(total / count) / 32768,
            "clipped_fraction": clipped / count}


def speech_measurements(frames: list[bytes], *, noise_rms: float) -> dict[str, float]:
    """Measure voiced level without letting calibration pre/post-roll dilute it.

    Always retain the worst peak and clipped *frame* from the complete acoustic
    segment. A brief clipped syllable must not disappear in a seven-second
    average, even when the longer phrase has a comfortable RMS.
    """
    if not frames or len(frames) > 28 or not 0 <= noise_rms <= 1:
        raise ValueError("Invalid acoustic calibration segment")
    levels = [pcm_measurements(frame) for frame in frames]
    voiced = [level for level in levels
              if level["rms"] >= max(.0006, noise_rms * 2.5)
              and level["peak"] >= max(.005, noise_rms * 4)]
    chosen = voiced or levels
    return {"rms": math.sqrt(sum(level["rms"] ** 2 for level in chosen) / len(chosen)),
            "peak": max(level["peak"] for level in levels),
            "dc": median(level["dc"] for level in levels),
            "clipped_fraction": max(level["clipped_fraction"] for level in levels)}


def room_noise_level(floors: list[float]) -> float | None:
    """Use the upper quartile of quiet-room intervals, not their best moment."""
    valid = sorted(value for value in floors if math.isfinite(value) and 0 < value <= 1)
    if not valid:
        return None
    return valid[math.ceil(.75 * len(valid)) - 1]


def derive_profile(room_floors: list[float], speech_samples: list[dict],
                   *, room_low_fractions: list[float] | None = None) -> AudioProfile:
    """Choose gentle conditioning only from a clean, complete calibration.

    A noisy/low-SNR room needs microphone placement or source repair, not
    digital gain that raises noise together with speech. A clipped source must
    be fixed at the hardware mixer, not digitally attenuated after clipping.
    """
    # Acoustic evidence must not depend on Vosk hearing words or the command
    # parser accepting an intent: the point is to help those earlier stages.
    valid = [item for item in speech_samples if item.get("acoustic_speech", True) and
             .0005 <= item.get("rms", 0) <= 1 and .005 < item.get("peak", 0) <= 1]
    floors = [value for value in room_floors if math.isfinite(value) and 0 < value <= 1]
    if len(valid) < 3 or len(floors) < 3:
        return AudioProfile(quality="bypass")
    noise = room_noise_level(floors)
    assert noise is not None  # At least three valid floors above.
    speech = median(item["rms"] for item in valid)
    peak = median(item["peak"] for item in valid)
    clipped = max(item.get("clipped_fraction", 0) for item in valid)
    dc = median(item.get("dc", 0) for item in valid)
    low_fractions = [value for value in (room_low_fractions or [])
                     if math.isfinite(value) and 0 <= value <= 1]
    low_fraction = (median(low_fractions) if len(low_fractions) >= 3 else None)
    snr = 20 * math.log10(max(speech, .00001) / max(noise, .00001))
    # One damaged spoken sample is enough to reject amplification. A median
    # peak would hide intermittent clipping, and filtering clipped rows out
    # altogether would accidentally call the remaining phrases "clean".
    if clipped > .002 or any(item["peak"] >= .95 for item in valid):
        return AudioProfile(1, False, noise, speech, snr, "clipped", low_fraction)
    if snr < 10 or noise >= .012:
        return AudioProfile(1, False, noise, speech, snr, "noisy", low_fraction)
    # A large swing during an otherwise quiet-room window means the baseline
    # is not a stable reference. It may be transient noise or upstream AGC
    # settling; do not infer which or calibrate gain from that window.
    if max(floors) > min(floors) * 4:
        return AudioProfile(1, False, noise, speech, snr, "unstable", low_fraction)
    gain = 1.0
    if peak < .38 and speech < .04:
        gain = min(2.0, .65 / max(peak, .1))
        gain = max(1.0, math.floor(gain * 4) / 4)
    # A persistent DC component is not speech; filter only when measured.
    high_pass = (dc >= .012 and dc >= speech * .22) or (
        low_fraction is not None and low_fraction >= .30)
    quality = "quiet" if gain > 1 else "clear"
    return AudioProfile(gain, high_pass, noise, speech, snr, quality, low_fraction)


class AudioPreprocessor:
    def __init__(self, profile: AudioProfile = AudioProfile()):
        self.profile = profile
        self.previous_input = 0.0
        self.previous_output = 0.0
        # A wake phrase may last less than the old one-second gain ramp. The
        # profile was measured during setup, so use it from the first frame;
        # process() still reduces it immediately when a loud frame arrives.
        self.applied_gain = profile.gain

    def reset(self, profile: AudioProfile | None = None) -> None:
        if profile is not None:
            self.profile = profile
        self.previous_input = self.previous_output = 0.0
        self.applied_gain = self.profile.gain

    def process(self, pcm: bytes) -> bytes:
        if self.profile.gain == 1 and not self.profile.high_pass:
            return pcm
        if len(pcm) < 2 or len(pcm) % 2:
            raise ValueError("PCM must contain whole 16-bit samples")
        samples = array("h")
        samples.frombytes(pcm)
        if sys.byteorder != "little":
            samples.byteswap()
        # Gain rises gradually, but drops immediately for sudden loud sounds.
        raw_peak = max(abs(value) for value in samples) / 32768
        target = min(self.profile.gain, .90 / max(raw_peak, .0001))
        self.applied_gain = min(target, self.applied_gain + .25)
        output = array("h")
        for sample in samples:
            value = float(sample)
            if self.profile.high_pass:
                filtered = HIGH_PASS_ALPHA * (self.previous_output + value - self.previous_input)
                self.previous_input = value
                self.previous_output = filtered
                value = filtered
            output.append(max(-32768, min(32767, round(value * self.applied_gain))))
        if sys.byteorder != "little":
            output.byteswap()
        return output.tobytes()


class CalibrationSegmenter:
    """Bounded acoustic phrase boundaries, independent of ASR endpoints.

    Only used during an owner-initiated voice check. It cannot authorize a
    command; the returned frames are subsequently evaluated by both decoders.
    Frames are 250 ms at 16 kHz. Keep a little leading room sound so initial
    consonants are not cut off, and always finish after seven seconds.
    """

    def __init__(self):
        self.preroll: list[tuple[bytes, bytes]] = []
        self.frames: list[tuple[bytes, bytes]] = []
        self.loud_frames = 0
        self.quiet_frames = 0

    def reset(self) -> None:
        self.preroll.clear()
        self.frames.clear()
        self.loud_frames = self.quiet_frames = 0

    def feed(self, raw: bytes, processed: bytes, *, noise_rms: float) -> tuple[list[bytes], list[bytes]] | None:
        if len(raw) != 8000 or len(processed) != 8000:
            raise ValueError("Calibration requires complete quarter-second frames")
        if not 0 <= noise_rms <= 1:
            raise ValueError("Invalid room-noise level")
        level = pcm_measurements(raw)
        loud = (level["rms"] >= max(.0006, noise_rms * 2.5)
                and level["peak"] >= max(.005, noise_rms * 4))
        pair = (raw, processed)
        if not self.frames:
            self.preroll.append(pair)
            self.preroll = self.preroll[-4:]
            self.loud_frames = self.loud_frames + 1 if loud else 0
            if self.loud_frames >= 2:
                self.frames = list(self.preroll)
                self.preroll.clear()
                self.quiet_frames = 0
            return None
        self.frames.append(pair)
        if loud:
            self.loud_frames += 1
            self.quiet_frames = 0
        else:
            self.quiet_frames += 1
        if self.quiet_frames < 3 and len(self.frames) < 28:
            return None
        completed = list(self.frames)
        self.reset()
        return [frame[0] for frame in completed], [frame[1] for frame in completed]
