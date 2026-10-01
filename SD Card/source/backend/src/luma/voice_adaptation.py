"""Owner-confirmed, offline correction of repeatable ASR phrase errors.

This does not retrain the acoustic model. It safely maps a repeatedly heard
post-wake phrase to one fixed, reversible or read-only command. Only salted
digests of the mishearing are persisted, never raw audio or transcripts.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets

from .voice import parse_local_command


LEARNABLE = frozenset({
    'change theme to arcade',
    'what time is it',
    'good morning',
    "what's the weather tomorrow",
    "what's the time",
    'when is my next event',
})
MAX_ENTRIES = 32
UNSAFE_WORDS = frozenset({
    "don't", 'dont', 'not', 'never', 'brightness', 'volume', 'timer', 'cancel',
    'delete', 'forget', 'privacy', 'screen', 'scene', 'zero', 'one', 'two',
    'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten',
    'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty',
    'ninety', 'hundred',
})


def normalized_phrase(text: str) -> str:
    if not isinstance(text, str) or len(text) > 160:
        return ''
    words = re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", text.casefold())
    if not 2 <= len(words) <= 16:
        return ''
    if any(word in UNSAFE_WORDS or word.isdigit() for word in words):
        return ''
    return ' '.join(words)


def conflicts_with_existing_command(heard: str, canonical: str) -> bool:
    """Never train a mishearing that would hijack an existing valid command."""
    existing = parse_local_command(heard)
    target = parse_local_command(canonical)
    return bool(existing and target and
                (existing.name, existing.value) != (target.name, target.value))


class PhraseAdaptations:
    def __init__(self, value: object = None):
        self.salt = secrets.token_hex(16)
        self.entries: dict[str, str] = {}
        if not isinstance(value, dict) or value.get('version') != 1:
            return
        salt, entries = value.get('salt'), value.get('entries')
        if not (isinstance(salt, str) and re.fullmatch(r'[0-9a-f]{32}', salt)
                and isinstance(entries, dict) and len(entries) <= MAX_ENTRIES):
            return
        if not all(isinstance(key, str) and re.fullmatch(r'[0-9a-f]{64}', key)
                   and isinstance(canonical, str) and canonical in LEARNABLE
                   for key, canonical in entries.items()):
            return
        self.salt, self.entries = salt, entries.copy()

    def _digest(self, heard: str) -> str:
        return hmac.new(bytes.fromhex(self.salt), heard.encode('utf-8'), hashlib.sha256).hexdigest()

    def resolve(self, heard: str) -> str | None:
        phrase = normalized_phrase(heard)
        learned = self.entries.get(self._digest(phrase)) if phrase else None
        # Also protects old saved entries if command parsing grows in a later
        # release. Raw phrases are not retained, so validate at use time.
        return None if learned and conflicts_with_existing_command(phrase, learned) else learned

    def add(self, heard: str, canonical: str) -> bool:
        phrase = normalized_phrase(heard)
        if not phrase or canonical not in LEARNABLE or conflicts_with_existing_command(phrase, canonical):
            return False
        digest = self._digest(phrase)
        if digest in self.entries and self.entries[digest] != canonical:
            return False
        if digest not in self.entries and len(self.entries) >= MAX_ENTRIES:
            return False
        self.entries[digest] = canonical
        return True

    def public(self) -> dict:
        """Local voice agent needs this matcher; no phrase text is included."""
        return {'version': 1, 'salt': self.salt, 'entries': self.entries.copy()}
