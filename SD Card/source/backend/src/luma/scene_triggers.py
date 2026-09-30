"""Boot-local transition monitors. No scheduling missed work or device access.

The caller supplies authoritative authenticated phone evidence, not UI privacy,
PIN, Tailscale or token refresh. None denotes unavailable/unknown evidence.
Regular observations (at most five seconds apart) are required: suspension or a
stalled worker establishes a new baseline rather than replaying a missed event.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from uuid import uuid4

from .scenes import utc


@dataclass(frozen=True)
class SceneTrigger:
    scene: str
    source: str
    occurrence: str
    observed_at: datetime


class PresenceTriggers:
    def __init__(self):
        self.reset()

    def reset(self):
        self.identity = self.last = self.stable = self.candidate = self.since = None

    def observe(self, connected, *, identity, monotonic, now, trusted):
        if (trusted is not True or type(connected) is not bool or not isinstance(identity, str)
                or not identity or type(monotonic) not in (int, float) or not isfinite(monotonic)):
            self.reset()
            return None
        now = utc(now)
        if self.last is None or identity != self.identity or not 0 <= monotonic - self.last <= 5:
            self.identity, self.last, self.stable = identity, monotonic, connected
            self.candidate = self.since = None
            return None  # Boot/re-pair/recovery is not an arrival or departure.
        self.last = monotonic
        if connected == self.stable:
            self.candidate = self.since = None
            return None
        if connected != self.candidate:
            self.candidate, self.since = connected, monotonic
        delay = 30 if connected else 180
        if monotonic - self.since < delay:
            return None
        self.stable = connected
        self.candidate = self.since = None
        return SceneTrigger('arrive' if connected else 'away', 'presence', str(uuid4()), now)


class CalendarTriggers:
    """Only continuously observed fresh selected-calendar Sleep boundaries.

    Input is the merged sleep interval containing now (start, end), or None for
    awake. The caller filters exact selected calendars/title/cancellations. A
    settings revision change, stale feed, jump or initial load is a new baseline.
    """
    def __init__(self):
        self.reset()

    def reset(self):
        self.revision = self.last = self.last_wall = self.interval = None

    def observe(self, interval, *, revision, monotonic, now, trusted, fresh):
        if (trusted is not True or fresh is not True or not isinstance(revision, str) or not revision
                or type(monotonic) not in (int, float) or not isfinite(monotonic)):
            self.reset()
            return None
        now = utc(now)
        if interval is not None:
            if not isinstance(interval, tuple) or len(interval) != 2:
                raise ValueError('Supply a merged Sleep interval.')
            interval = tuple(utc(value) for value in interval)
            if not interval[0] <= now < interval[1]: raise ValueError('Sleep interval must contain now.')
        if (self.last is None or revision != self.revision or not 0 <= monotonic - self.last <= 5
                or abs((now - self.last_wall).total_seconds() - (monotonic - self.last)) > 2):
            self.revision, self.last, self.last_wall, self.interval = revision, monotonic, now, interval
            return None
        previous, previous_wall = self.interval, self.last_wall
        self.last, self.last_wall, self.interval = monotonic, now, interval
        # An inserted/deleted/shortened event is not passage through a previously
        # observed boundary. Longer merged sleep intervals do not wake early.
        if previous is None and interval is not None and previous_wall < interval[0] <= now:
            return SceneTrigger('night', 'calendar', str(uuid4()), now)
        if previous is not None and interval is None and previous_wall < previous[1] <= now:
            return SceneTrigger('morning', 'calendar', str(uuid4()), now)
        return None
