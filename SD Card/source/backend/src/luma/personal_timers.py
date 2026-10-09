"""Independent durable profile timers alongside the legacy shared room timer."""
from __future__ import annotations

from time import monotonic

from .focus_timer import FocusTimer
from .profiles import ProfileRepository


class PersonalTimers:
    def __init__(self, profiles: ProfileRepository, *, clock=monotonic):
        self.profiles, self.clock = profiles, clock
        self._timers: dict[str, FocusTimer] = {}

    def for_user(self, uid: str) -> FocusTimer:
        self.profiles.get(uid)
        if uid not in self._timers:
            self._timers[uid] = FocusTimer(self.profiles.account_storage(uid), clock=self.clock,
                                          cache_namespace='personal_timer')
        return self._timers[uid]

    def tick(self, now=None, *, trusted=None) -> bool:
        live = {user.id for user in self.profiles.list()}
        # Removing a user also cancels that user's pending completion cue.
        self._timers = {uid: timer for uid, timer in self._timers.items() if uid in live}
        changed = False
        for uid in live:
            changed = self.for_user(uid).tick(now, trusted=trusted) or changed
        return changed

    def snapshot(self, present: set[str]) -> list[dict]:
        result = []
        for user in self.profiles.list():
            timer = self.for_user(user.id).snapshot(private=user.id not in present)
            if timer['status'] != 'idle':
                result.append({'profile_id': user.id, 'owner': user.nickname,
                               'owner_present': user.id in present, **timer})
        return result

    def claim_chime(self, *, muted=False) -> bool:
        # Consume all simultaneous completions into one five-second alarm;
        # never play each person's cue in a long queue or replay while muted.
        play = False
        for user in self.profiles.list():
            play = self.for_user(user.id).claim_chime(muted=muted) or play
        return play

    def chime_pending(self) -> bool:
        return any(self.for_user(user.id).chime_pending() for user in self.profiles.list())
