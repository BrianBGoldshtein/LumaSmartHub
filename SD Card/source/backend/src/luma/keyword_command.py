"""Bounded ASR word alignment after independently verified acoustic wake.

No name aliases, waveform slicing, command execution or identity decision.
Word timestamps remove the rare-name prefix without relying on its spelling.
Keep boundary words (especially negation), rather than trimming by a guessed
whole-word duration after the final phoneme's *start*.
"""
from dataclasses import dataclass
import json
import math
import re

from .keyword_wake import KeywordEvidence, KeywordWakeError, validate_audio

BOUNDARY_MARGIN_SECONDS = .08


@dataclass(frozen=True)
class TimedWord:
    word: str
    start: float
    end: float


@dataclass(frozen=True)
class TimedTranscript:
    text: str
    words: tuple[TimedWord, ...]


def timed_transcript(recognizer_factory, frames) -> TimedTranscript:
    """Fresh ASR timestamps from the same complete <=9s PCM as the spotter.

    Vosk Reset retains cumulative timestamps. Use a NEW recognizer sharing
    the loaded Model for each replay, so its clock really starts at zero.
    No partial result can qualify a command. Fixed failures contain no words.
    """
    duration = validate_audio(frames)
    words: list[TimedWord] = []
    texts: list[str] = []

    def append_result(raw):
        if not isinstance(raw, str) or len(raw) > 16384:
            raise ValueError
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError
        text = value.get('text', '')
        rows = value.get('result', [])
        if not isinstance(text, str) or len(text) > 512 or not isinstance(rows, list) or len(rows) > 64:
            raise ValueError
        part: list[TimedWord] = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError
            word, start, end = row.get('word'), row.get('start'), row.get('end')
            if (not isinstance(word, str) or not re.fullmatch(r"[a-z0-9]+(?:'[a-z0-9]+)?|\[unk\]", word)
                    or type(start) not in (int, float) or type(end) not in (int, float)
                    or not math.isfinite(start) or not math.isfinite(end)
                    or not 0 <= start <= end <= duration + .03):
                raise ValueError
            prior = part[-1] if part else words[-1] if words else None
            if prior and (start < prior.start or end < prior.end or start < prior.end - .03):
                raise ValueError
            part.append(TimedWord(word, float(start), float(end)))
        if ' '.join(item.word for item in part) != ' '.join(text.split()):
            raise ValueError  # no untimed words can leak into command selection
        words.extend(part)
        if len(words) > 64:
            raise ValueError
        if text:
            texts.append(text)

    try:
        recognizer = recognizer_factory()
        recognizer.SetWords(True)
        for frame in frames:
            if recognizer.AcceptWaveform(frame):
                append_result(recognizer.Result())
        append_result(recognizer.FinalResult())
        return TimedTranscript(' '.join(texts), tuple(words))
    except KeywordWakeError:
        raise
    except Exception:
        raise KeywordWakeError('keyword_alignment_unavailable') from None


def command_after_keyword(transcript: TimedTranscript, evidence: KeywordEvidence,
                          *, duration: float, check_prefix=True) -> str:
    first, last = evidence.first_token_seconds, evidence.last_token_seconds
    if (evidence.detected is not True or type(first) not in (int, float)
            or type(last) not in (int, float) or not math.isfinite(first)
            or not math.isfinite(last) or not math.isfinite(duration)
            or not 0 <= first <= last <= duration or not 0 < duration <= 9):
        raise KeywordWakeError('keyword_result_invalid')
    # An acoustic start guard alone allows a short quoted wake inside speech.
    # Permit natural hesitation, not "I said/don't say Hey Luma". This check
    # does not require either ASR decoder to spell the actual wake name.
    prefix = [item.word for item in transcript.words if item.end < first - .02]
    if check_prefix and (len(prefix) > 2 or any(
            word not in {'um', 'uh', 'oh', 'ok', 'okay', 'please'} for word in prefix)):
        raise KeywordWakeError('keyword_prefix_rejected')
    # The last phone's timestamp is a START, not an end. Never add a made-up
    # .2s name duration that could erase a tightly joined "don't". An 80ms
    # overlap allowance accounts for differing phone/ASR frame alignment;
    # a real synthetic timer's verb started 50ms before the last phone stamp.
    tail = [item.word for item in transcript.words if item.start >= last - BOUNDARY_MARGIN_SECONDS]
    # Preserve negation even if the ASR interval overlaps the name boundary.
    # Positive requests lose no title/timer words; uncertain negated input is
    # vetoed rather than rewritten into a positive command.
    if any(item.word in {"don't", 'dont', 'not', 'never'}
           and item.end >= first and item.start < last - BOUNDARY_MARGIN_SECONDS for item in transcript.words):
        raise KeywordWakeError('keyword_negation_overlap')
    return ' '.join(tail)
