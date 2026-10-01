"""Independent wake corroboration for the offline recognizers.

The constrained Vosk grammar is useful for commands but can force unrelated
speech into its small vocabulary. Requiring the unrestricted decoder to hear
the wake phrase is an optional false-activation filter, not voice identity.
"""
from __future__ import annotations

import re


MODES = frozenset({'standard', 'dual_decoder'})


def read_wake_mode(value: object) -> str:
    if (isinstance(value, dict) and value.get('version') == 1
            and value.get('mode') in MODES):
        return value['mode']
    return 'standard'


def has_wake(text: str, phrase: str = 'hey luma') -> bool:
    if not isinstance(text, str):
        return False
    words = re.sub(r'\s+', ' ', text.casefold()).strip()
    return bool(re.search(r'\b' + re.escape(phrase.casefold().strip()) + r'\b', words))


def command_after_wake(text: str, phrase: str = 'hey luma') -> str | None:
    if not isinstance(text, str):
        return None
    words = re.sub(r'\s+', ' ', text.casefold()).strip()
    match = re.search(r'\b' + re.escape(phrase.casefold().strip()) + r'\b', words)
    return words[match.end():].strip(' ,.!?') if match else None


def wake_confirmed(constrained: str, unrestricted: str, mode: str,
                   phrase: str = 'hey luma') -> bool:
    """Call only when the constrained decoder has proposed a new wake.

    A command in an already-open, verified wake window does not need to repeat
    the phrase. Failure is conservative: no command is executed.
    """
    if not has_wake(constrained, phrase):
        return False
    return mode != 'dual_decoder' or has_wake(unrestricted, phrase)
