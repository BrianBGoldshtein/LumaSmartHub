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
MAX_FAMILIES = 16
MAX_FUZZY_GRAMS = 96
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
        self.families: list[dict] = []
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
        families = value.get('families', [])
        if (not isinstance(families, list) or len(families) > MAX_FAMILIES
                or any(not isinstance(family, dict) or set(family) != {'canonical', 'variants'}
                       or not isinstance(family['canonical'], str)
                       or family['canonical'] not in LEARNABLE
                       or not isinstance(family['variants'], list)
                       or len(family['variants']) != 2
                       or any(not isinstance(signature, list)
                              or not 3 <= len(signature) <= MAX_FUZZY_GRAMS
                              or any(not isinstance(gram, str)
                                     or re.fullmatch(r'[0-9a-f]{16}', gram) is None
                                     for gram in signature)
                              or signature != sorted(set(signature))
                              for signature in family['variants'])
                       for family in families)):
            return
        self.salt, self.entries = salt, entries.copy()
        self.families = [{'canonical': family['canonical'],
                          'variants': [list(signature) for signature in family['variants']]}
                         for family in families]

    def _digest(self, heard: str) -> str:
        return hmac.new(bytes.fromhex(self.salt), heard.encode('utf-8'), hashlib.sha256).hexdigest()

    def _signature(self, phrase: str) -> list[str]:
        grams = {phrase[index:index + 3] for index in range(max(0, len(phrase) - 2))}
        if not 3 <= len(grams) <= MAX_FUZZY_GRAMS:
            return []
        key = bytes.fromhex(self.salt)
        return sorted({hmac.new(key, gram.encode('utf-8'), hashlib.sha256).hexdigest()[:16]
                       for gram in grams})

    @staticmethod
    def _similarity(left: set[str], right: set[str]) -> float:
        return len(left & right) / len(left | right) if left and right else 0.0

    def resolve(self, heard: str) -> str | None:
        phrase = normalized_phrase(heard)
        learned = self.entries.get(self._digest(phrase)) if phrase else None
        # Also protects old saved entries if command parsing grows in a later
        # release. Raw phrases are not retained, so validate at use time.
        if learned:
            return None if conflicts_with_existing_command(phrase, learned) else learned
        # Approximate matching is limited to two separately confirmed
        # mishearings of a safe command. A supported command always wins; a
        # fuzzy correction may never reinterpret an existing valid phrase.
        if not phrase or parse_local_command(phrase) is not None:
            return None
        signature = set(self._signature(phrase))
        if not signature:
            return None
        candidates = []
        for family in self.families:
            scores = [self._similarity(signature, set(variant))
                      for variant in family['variants']]
            if min(scores) >= .80 and max(scores) >= .90:
                candidates.append((max(scores), family['canonical']))
        candidates.sort(reverse=True)
        if not candidates or (len(candidates) > 1 and candidates[0][0] - candidates[1][0] < .08):
            return None
        return candidates[0][1]

    def add(self, heard: str, canonical: str) -> bool:
        return self.add_many([heard], canonical)

    def add_many(self, heard_phrases: list[str], canonical: str) -> bool:
        """Atomically save owner-confirmed variants of one safe intent."""
        if not 1 <= len(heard_phrases) <= 2 or canonical not in LEARNABLE:
            return False
        phrases = [normalized_phrase(heard) for heard in heard_phrases]
        if (any(not phrase or conflicts_with_existing_command(phrase, canonical)
                for phrase in phrases)):
            return False
        digests = {self._digest(phrase) for phrase in phrases}
        if any(digest in self.entries and self.entries[digest] != canonical
               for digest in digests):
            return False
        if len(self.entries) + len(digests - self.entries.keys()) > MAX_ENTRIES:
            return False
        self.entries.update({digest: canonical for digest in digests})
        if len(phrases) == 2 and phrases[0] != phrases[1] and len(self.families) < MAX_FAMILIES:
            signatures = [self._signature(phrase) for phrase in phrases]
            if all(signatures) and not any(
                    family['canonical'] == canonical and family['variants'] == signatures
                    for family in self.families):
                self.families.append({'canonical': canonical, 'variants': signatures})
        return True

    def public(self) -> dict:
        """Local voice agent needs this matcher; no phrase text is included."""
        return {'version': 1, 'salt': self.salt, 'entries': self.entries.copy(),
                'families': [{'canonical': family['canonical'],
                              'variants': [list(signature) for signature in family['variants']]}
                             for family in self.families]}
