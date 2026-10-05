"""Independent wake corroboration for the offline recognizers.

The constrained Vosk grammar is useful for commands but can force unrelated
speech into its small vocabulary. The phonetic listener is the new protected
default. Older decoder choices remain explicit escape hatches, not identity.
"""
from __future__ import annotations

import re


MODES = frozenset({'standard', 'dual_decoder', 'acoustic'})


def read_wake_mode(value: object) -> str:
    # v1 standard was a permissive default, not affirmative consent. v2's
    # protected default is superseded by acoustic protection; preserve an
    # affirmative v2 more-sensitive choice. All v3 choices are explicit.
    if isinstance(value, dict) and type(value.get('version')) is int:
        if value['version'] == 3 and value.get('mode') in MODES:
            return value['mode']
        if value['version'] == 2 and value.get('mode') == 'standard':
            return 'standard'
    return 'acoustic'  # unavailable/failed assets fail closed, never sensitive


class WakeAudioBuffer(list[bytes]):
    """Bounded replay; never compare full speech against only its last 9s."""
    def __init__(self):
        super().__init__()
        self.complete = True

    def append(self, frame: bytes) -> None:
        super().append(frame)
        if len(self) > 36:
            self.pop(0)
            self.complete = False

    def clear(self) -> None:
        super().clear()
        self.complete = True


def has_wake(text: str, phrase: str = 'hey luma') -> bool:
    if not isinstance(text, str):
        return False
    words = re.sub(r'\s+', ' ', text.casefold()).strip()
    return bool(re.search(r'\b' + re.escape(phrase.casefold().strip()) + r'\b', words))


def wake_near_start(text: str, phrase: str = 'hey luma') -> bool:
    """Reject a wake quoted deep inside unrelated speech in strict mode.

    An optional short lead-in accommodates a natural hesitation. Unknown
    words may conceal arbitrary call/TV conversation; do not skip them.
    """
    if not isinstance(text, str):
        return False
    words = re.findall(r'[a-z0-9]+', text.casefold())
    wake_words = re.findall(r'[a-z0-9]+', phrase.casefold())
    if not wake_words:
        return False
    for prefix_length in range(min(2, len(words) - len(wake_words)) + 1):
        if (all(word in {'um', 'uh', 'oh', 'ok', 'okay', 'please'}
                for word in words[:prefix_length])
                and words[prefix_length:prefix_length + len(wake_words)] == wake_words):
            return True
    return False


def command_after_wake(text: str, phrase: str = 'hey luma') -> str | None:
    if not isinstance(text, str):
        return None
    words = re.sub(r'\s+', ' ', text.casefold()).strip()
    match = re.search(r'\b' + re.escape(phrase.casefold().strip()) + r'\b', words)
    return words[match.end():].strip(' ,.!?') if match else None


def wake_confirmed(constrained: str, unrestricted: str, mode: str,
                   phrase: str = 'hey luma', *, complete: bool = True) -> bool:
    """Call only when the constrained decoder has proposed a new wake.

    A command in an already-open, verified wake window does not need to repeat
    the phrase. Failure is conservative: no command is executed.
    """
    if not complete or not wake_near_start(constrained, phrase):
        return False
    return mode == 'standard' or wake_near_start(unrestricted, phrase)
