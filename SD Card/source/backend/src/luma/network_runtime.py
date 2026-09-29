"""Ephemeral connectivity status; never changes privacy, sleep or saved data."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from time import monotonic

from .network import network_request


class NetworkRuntime:
    def __init__(self, request=network_request):
        self.request = request
        self.state = "unknown"
        self.checked_at = None
        self.checked_clock = None
        self.checking_enabled = False
        self.pending = None
        self.pending_count = 0

    def snapshot(self):
        stale = self.checked_clock is None or monotonic() - self.checked_clock > 100
        return {"state": "unknown" if stale else self.state,
                "checked_at": self.checked_at, "checking_enabled": self.checking_enabled,
                "stale": stale}

    async def poll(self):
        try:
            result = await asyncio.wait_for(self.request({"action": "status"}), 12)
            state = result["state"]
            if state not in {"offline", "portal", "limited", "online", "unknown"}:
                raise ValueError("Invalid connectivity state")
            self.checking_enabled = result["checking_enabled"] is True
        except (ValueError, KeyError, TypeError, OSError, TimeoutError):
            state = "unavailable"
            self.checking_enabled = False
        self.checked_clock = monotonic()
        self.checked_at = datetime.now(UTC).isoformat()
        # Two consecutive trouble readings avoid flashing a warning during
        # short roaming/DHCP transitions. Recovery clears it immediately.
        if state in {"online", "unknown", "unavailable"}:
            self.state = state
            self.pending = None
            self.pending_count = 0
        else:
            self.pending_count = self.pending_count + 1 if self.pending == state else 1
            self.pending = state
            if self.pending_count >= 2:
                self.state = state

    async def run(self):
        while True:
            await self.poll()
            await asyncio.sleep(30)
