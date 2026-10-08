"""Fair, adapter-wide radio jobs; authorization remains per ANCS session."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from random import uniform
from time import monotonic


class RadioScheduler:
    def __init__(self, *, clock=monotonic, jitter=uniform):
        self.clock, self.jitter = clock, jitter
        self._locks: dict[str, asyncio.Lock] = {}
        self._pending: set[str] = set()
        self._scans: dict[str, float] = {}
        self._failures: dict[str, int] = {}
        self._stable: dict[str, float] = {}

    async def perform(self, uid: str, adapter: str, operation: Callable[[], Awaitable],
                      *, scan=False, connect: Callable[[], Awaitable] | None = None):
        # Each phone has one worker; reject accidental duplicate jobs rather
        # than letting it fill the FIFO ahead of other registered users.
        if uid in self._pending:
            raise RuntimeError('A radio operation for this user is already pending.')
        self._pending.add(uid)
        lock = self._locks.setdefault(adapter, asyncio.Lock())
        try:
            async with lock:  # asyncio locks wake waiters in arrival order.
                due = self.clock() - self._scans.get(adapter, float('-inf')) >= 30
                # Existing link helpers bound cancellation/cleanup too. This
                # outer ceiling ensures a broken transport cannot starve peers.
                async with asyncio.timeout(120):
                    if scan and not due:
                        return await connect() if connect is not None else False
                    if scan:
                        self._scans[adapter] = self.clock()
                    return await operation()
        finally:
            self._pending.discard(uid)

    def note_authorized(self, uid: str):
        start = self._stable.setdefault(uid, self.clock())
        if self.clock() - start >= 60:
            self._failures.pop(uid, None)

    def failure_delay(self, uid: str) -> float:
        self._stable.pop(uid, None)
        failures = min(5, self._failures.get(uid, 0) + 1)
        self._failures[uid] = failures
        return min(120, 10 * 2 ** (failures - 1)) * self.jitter(.9, 1.1)

    def forget(self, uid: str):
        self._failures.pop(uid, None)
        self._stable.pop(uid, None)
