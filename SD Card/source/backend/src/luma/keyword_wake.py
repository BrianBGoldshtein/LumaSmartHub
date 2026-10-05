"""Bounded acoustic verifier used by the explicitly selected phonetic mode.

This separates a keyword model's evidence from ASR spelling and command
authorization. It requires a signed ARM64 asset and isolated runtime; real
owner positive/negative acceptance is still unproven. Never
silently import an optional model or replace a failed check with acceptance.
"""
from array import array
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import sys
import tempfile
from time import monotonic


RATE = 16000
MAX_FRAMES = 36
FRAME_BYTES = 8000
KEYWORD = 'HEY_LUMA'
NON_WAKE_KEYWORDS = frozenset({'HEY_LUNA', 'NO_WAKE_LAURA', 'NO_WAKE_THEY_BLOOM',
                              'NO_WAKE_LUIS', 'NO_WAKE_LUCY'})
KEYWORDS_CONFIG = ('HH EY1 L UW1 M AH0 @HEY_LUMA\n'
                   'HH EY1 L UW1 N AH0 @HEY_LUNA\n'
                   'HH EY1 L AO1 R AH0 @NO_WAKE_LAURA\n'
                   'DH EY1 B L UW1 M @NO_WAKE_THEY_BLOOM\n'
                   'HH EY1 L UW0 IY1 S @NO_WAKE_LUIS\n'
                   'HH EY1 L UW1 S IY0 @NO_WAKE_LUCY\n')
# The six-phone target must be contiguous, not assembled from a nearby name
# and an M/A sound in a later word. This bound is deliberately larger than
# measured synthetic name gaps (.20s); actual owner pronunciation is unproven.
MAX_NAME_PHONE_GAP_SECONDS = .45
PREFIX = 'epoch-13-avg-2-chunk-16-left-64'
# Exact author-distributed FP32 files; no g2p dictionary is needed.
MODEL_PINS = {
    f'encoder-{PREFIX}.onnx': '540ff509ed89bd22afe04bf7049a54bb1c95c6d8a18742ea9691910cdb5f859e',
    f'decoder-{PREFIX}.onnx': '63a22dd60f40fff082ac3e09afa507f6787da36df76ded2fbe145fa233e22c21',
    f'joiner-{PREFIX}.onnx': '76f7a24ed0c08633af14b2ee377f747af880d3b65eeba2cd3f31f3380fb73e8d',
    'tokens.txt': '2d3f32311f9b692b964da3c90e830258d3e78e013cb0c992dbfb15cd5a1a71b0',
}


class KeywordWakeError(RuntimeError):
    """Fixed failure reason; never include PCM, transcript or upstream errors."""


@dataclass(frozen=True)
class KeywordEvidence:
    detected: bool
    first_token_seconds: float | None = None
    last_token_seconds: float | None = None


def validate_audio(frames, *, complete=True) -> float:
    """Validate before copying PCM or starting an optional worker."""
    if (complete is not True or getattr(frames, 'complete', True) is not True
            or not isinstance(frames, list)
            or not 1 <= len(frames) <= MAX_FRAMES
            or any(type(frame) is not bytes or not 0 < len(frame) <= FRAME_BYTES
                   or len(frame) % 2 for frame in frames)):
        raise KeywordWakeError('keyword_audio_invalid')
    return sum(map(len, frames)) / (RATE * 2)


class KeywordVerifier:
    def __init__(self, spotter):
        self.spotter = spotter

    def verify(self, frames, *, complete=True) -> KeywordEvidence:
        """Replay a complete <=9s utterance with fresh state, never a tail.

        The five-second deadline bounds cooperative processing, not a native
        call that hangs. Production must put this adapter behind a killable
        worker. Evidence alone must never open a command/presence window.
        """
        seconds = validate_audio(frames, complete=complete)
        deadline = monotonic() + 5
        first = None
        last = None
        steps = 0
        try:
            stream = self.spotter.create_stream()
            for frame in [*frames, *(bytes(FRAME_BYTES) for _ in range(4))]:
                if monotonic() > deadline:
                    raise KeywordWakeError('keyword_decode_timeout')
                pcm = array('h', frame)
                if sys.byteorder != 'little':
                    pcm.byteswap()
                stream.accept_waveform(RATE, [value / 32768 for value in pcm])
                while self.spotter.is_ready(stream):
                    steps += 1
                    if steps > 2048 or monotonic() > deadline:
                        raise KeywordWakeError('keyword_decode_timeout')
                    self.spotter.decode_stream(stream)
                    # The pinned engine consumes a result when read. Calling
                    # get_result() then timestamps() reads it twice and loses
                    # the timestamp evidence. Read the public engine once.
                    result = self.spotter.keyword_spotter.get_result(stream)
                    keyword = result.keyword.strip()
                    if not keyword:
                        continue
                    times = result.timestamps
                    if (keyword not in NON_WAKE_KEYWORDS | {KEYWORD}
                            or not isinstance(times, (list, tuple))
                            or not times or any(type(t) not in (int, float)
                            or not math.isfinite(t) or not 0 <= t <= seconds + 1 for t in times)
                            or list(times) != sorted(times)):
                        raise KeywordWakeError('keyword_result_invalid')
                    if keyword == KEYWORD:
                        if len(times) != 6:
                            raise KeywordWakeError('keyword_result_invalid')
                        if all(b-a <= MAX_NAME_PHONE_GAP_SECONDS
                               for a,b in zip(times[2:],times[3:])):
                            if first is None or times[0] < first:
                                first, last = times[0], times[-1]
                    self.spotter.reset_stream(stream)
            return KeywordEvidence(first is not None, first, last)
        except KeywordWakeError:
            raise
        except Exception:
            raise KeywordWakeError('keyword_decode_failed') from None


def load_pinned_candidate(directory: Path) -> KeywordVerifier:
    """Research/qualification entry point only; no download or installation.

    Pins are not a substitute for a signed asset installer. The current
    application never calls this factory or claims the candidate is ready.
    """
    try:
        directory = directory.resolve(strict=True)
        for name, expected in MODEL_PINS.items():
            path = directory / name
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
                raise KeywordWakeError('keyword_model_invalid')
            with path.open('rb') as source:
                if hashlib.file_digest(source, 'sha256').hexdigest() != expected:
                    raise KeywordWakeError('keyword_model_invalid')
        import sherpa_onnx
        if sherpa_onnx.__version__ != '1.13.8':
            raise KeywordWakeError('keyword_runtime_invalid')
        with tempfile.TemporaryDirectory(prefix='luma-keyword-config-') as folder:
            keywords = Path(folder) / 'keywords.txt'
            # Trusted fixed config only; no microphone input is written.
            keywords.write_text(KEYWORDS_CONFIG, encoding='ascii')
            spotter = sherpa_onnx.KeywordSpotter(
                tokens=str(directory / 'tokens.txt'),
                encoder=str(directory / f'encoder-{PREFIX}.onnx'),
                decoder=str(directory / f'decoder-{PREFIX}.onnx'),
                joiner=str(directory / f'joiner-{PREFIX}.onnx'),
                keywords_file=str(keywords), num_threads=1, provider='cpu',
                keywords_score=3, keywords_threshold=.1, max_active_paths=8)
        return KeywordVerifier(spotter)
    except KeywordWakeError:
        raise
    except Exception:
        raise KeywordWakeError('keyword_model_unavailable') from None
