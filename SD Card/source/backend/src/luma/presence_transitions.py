"""Volatile wall greetings; never use their debounce as privacy authority."""
from __future__ import annotations

from secrets import randbelow
from time import monotonic


class PresenceTransitions:
    def __init__(self, *, clock=monotonic, startup_seconds=30):
        self.clock = clock
        self.startup_until = clock() + startup_seconds
        self.confirmed = None
        self.candidates = {}
        self.ready = {}
        self.active = None
        self.chimed = None

    def observe(self, names: dict[str, str], present: set[str], *, suppressed=False):
        now = self.clock()
        present = present & names.keys()
        # Reconstruct a baseline, not a greeting backlog, after boot/restart,
        # Sleep, manual off, update, or an alarm. Nothing is saved to the SD.
        if self.confirmed is None or now < self.startup_until or suppressed:
            changed = self.active is not None
            self.confirmed = set(present)
            self.candidates.clear()
            self.ready.clear()
            self.active = None
            return changed
        self.confirmed &= names.keys()
        self.candidates = {uid: value for uid, value in self.candidates.items() if uid in names}
        for uid in names:
            target = uid in present
            if target == (uid in self.confirmed):
                self.candidates.pop(uid, None)
                continue
            candidate = self.candidates.get(uid)
            if candidate is None or candidate[0] != target:
                candidate = self.candidates[uid] = (target, now)
            if now - candidate[1] >= (3 if target else 15):
                if target:
                    self.confirmed.add(uid)
                else:
                    self.confirmed.discard(uid)
                self.ready[uid] = target
                self.candidates.pop(uid, None)
        changed = False
        if self.active is not None:
            # Do not leave "arriving" visible after live authorization is lost,
            # or "has left" after a return. Privacy itself has no grace period.
            valid = {uid: target for uid, target in self.active['changes'].items()
                     if uid in names and (uid in present) == target}
            if valid != self.active['changes']:
                self.active['changes'] = valid
                changed = True
            if not valid or now >= self.active['until']:
                self.active = None
                changed = True
        self.ready = {uid: target for uid, target in self.ready.items()
                      if uid in names and (uid in present) == target}
        if self.active is None and self.ready:
            self.active = {'id': randbelow((1 << 52) - 1) + 1, 'until': now + 5,
                           'changes': self.ready.copy()}
            self.ready.clear()
            changed = True
        return changed

    def view(self, names: dict[str, str]):
        if not self.active:
            return None
        remaining = max(0, int((self.active['until'] - self.clock()) * 1000))
        if remaining == 0:
            return None
        return {'id': self.active['id'], 'remaining_ms': remaining,
                'arriving': [names[uid] for uid, target in self.active['changes'].items()
                             if target and uid in names],
                'leaving': [names[uid] for uid, target in self.active['changes'].items()
                            if not target and uid in names]}

    def claim_chime(self, *, audible):
        if not self.active or self.clock() >= self.active['until'] or self.chimed == self.active['id']:
            return False
        self.chimed = self.active['id']
        return audible
