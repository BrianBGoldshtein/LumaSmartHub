"""Conservative selected-purifier polling and nonqueued owner operations."""
import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from time import monotonic

from .purifier_adapter import (PurifierAdapter, PurifierBusy, PurifierRateLimit,
                               PurifierReconnect, PurifierUnavailable)


class RoomAccessChanged(PurifierUnavailable):
    pass


class RoomRuntime:
    def __init__(self, service, *, factory=PurifierAdapter, clock=monotonic, utcnow=None):
        self.service, self.store = service, service.room
        self.factory, self.clock = factory, clock
        self.utcnow = utcnow or (lambda: datetime.now(UTC))
        self.lock = asyncio.Lock()
        self.adapter = None
        self.adapter_generation = None
        self.catalog = []
        self.catalog_at = 0
        self.next_poll = self.next_setup = self.next_command = 0
        self.failures = 0
        self.needs_reconnect = False
        self.closed = False

    def owner_allowed(self):
        return not self.closed and (not self.service.settings.onboarding_completed or not self.service.snapshot()['privacy_redacted'])

    def _check(self, revision, generation, *, owner=True):
        if owner and not self.owner_allowed():
            raise RoomAccessChanged('Unlock Luma to configure or control room devices.')
        if self.closed:
            raise RoomAccessChanged('Room device service is stopping.')
        self.store.check(revision, generation)

    @asynccontextmanager
    async def _operation(self):
        if self.lock.locked():
            raise PurifierBusy('Another room-device operation is in progress. Nothing has been queued.')
        async with self.lock:
            yield

    def _setup_slot(self):
        if self.clock() < self.next_setup:
            raise PurifierRateLimit('Wait a few seconds before checking VeSync again.')
        self.next_setup = self.clock() + 5

    async def _ensure(self):
        if self.needs_reconnect:
            raise PurifierReconnect('Reconnect VeSync on this hub.')
        if self.adapter_generation != self.store.generation:
            if self.adapter:
                await self.adapter.close()
            self.adapter = None
            self.catalog = []
            saved = self.store.session
            if not saved:
                raise PurifierReconnect('Connect VeSync on this hub first.')
            self.adapter = self.factory(saved, timezone=self.service.settings.timezone)
            self.adapter_generation = self.store.generation
        return self.adapter

    def _failed(self, exc, generation, revision):
        if generation != self.store.generation or revision != self.store.revision:
            return
        self.failures = min(5, self.failures + 1)
        self.next_poll = self.clock() + min(1800, 120 * 2 ** (self.failures - 1))
        self.store.health = 'unavailable'
        if isinstance(exc, PurifierRateLimit):
            self.next_poll = self.clock() + 3600
            self.next_setup = self.next_command = self.next_poll
            self.store.health = 'rate_limited'
        if isinstance(exc, PurifierReconnect):
            self.needs_reconnect = True
            self.store.health = 'needs_reconnect'
        self.service.publish('room.updated')

    def _success(self):
        self.failures = 0
        self.next_poll = self.clock() + 120

    async def login(self, username, password, country, revision):
        generation = self.store.generation
        self._check(revision, generation)
        async with self._operation():
            self._setup_slot()
            candidate = self.factory(timezone=self.service.settings.timezone)
            try:
                saved = await candidate.login(username, password, country)
                self._check(revision, generation)
                self.store.set_session(saved, revision=revision, generation=generation)
            except Exception as exc:
                await candidate.close()
                # A failed new login does not mark a still-valid old account expired.
                if isinstance(exc, PurifierRateLimit): self.next_setup = self.clock() + 3600
                raise
            except asyncio.CancelledError:
                await candidate.close()
                raise
            old = self.adapter
            self.adapter = candidate
            self.adapter_generation = self.store.generation
            self.needs_reconnect = False
            self.catalog = []
            self.next_poll = self.next_command = 0
            self.failures = 0
            if old: await old.close()
            self.service.publish('room.updated')

    async def disconnect(self, revision):
        # Invalidate before waiting for adapter.close: an in-flight preflight read
        # must fail its can_send gate, and late results must not restore old state.
        generation = self.store.generation
        self._check(revision, generation)
        self.store.set_session(None, revision=revision, generation=generation)
        old, self.adapter = self.adapter, None
        self.adapter_generation = None
        self.needs_reconnect = False
        self.catalog = []
        self.service.publish('room.updated')
        if old: await old.close()

    async def discover(self, revision):
        generation = self.store.generation
        self._check(revision, generation)
        async with self._operation():
            self._setup_slot()
            try:
                adapter = await self._ensure()
                result = await adapter.discover()
                self._check(revision, generation)
            except PurifierUnavailable as exc:
                if not isinstance(exc, RoomAccessChanged): self._failed(exc, generation, revision)
                raise
            self.catalog, self.catalog_at = result, self.clock()
            return result

    async def select(self, identifier, name, revision):
        generation = self.store.generation
        self._check(revision, generation)
        async with self._operation():
            if identifier is None:
                self.store.select(None, revision=revision, generation=generation)
                self.service.publish('room.updated')
                return
            if self.adapter_generation != generation or self.clock() - self.catalog_at > 300:
                raise ValueError('Reload the device list before selecting a purifier.')
            item = next((row for row in self.catalog if row['id'] == identifier), None)
            if item is None: raise ValueError('Choose a purifier from the discovered list.')
            if self.clock() < self.next_command:
                raise PurifierRateLimit('Wait before checking the purifier again.')
            self.next_command = self.clock() + 5
            try:
                sample = await self.adapter.read(identifier)
                self._check(revision, generation)
                self.store.select({'id': identifier, 'name': name or item['name'], 'model': item['model']},
                                  revision=revision, generation=generation)
                self.store.report(sample, revision=self.store.revision, generation=generation)
            except PurifierUnavailable as exc:
                if not isinstance(exc, RoomAccessChanged): self._failed(exc, generation, revision)
                raise
            self._success()
            self.service.publish('room.updated')

    async def _selected_adapter(self):
        adapter = await self._ensure()
        selected = self.store.selected
        if not selected: raise ValueError('Select a purifier first.')
        if selected['id'] not in adapter.devices:
            await adapter.discover()
        return adapter, selected['id']

    async def refresh(self, *, manual=False):
        if self.closed or self.store.recovery_error or not self.store.selected or not self.store.session or self.needs_reconnect:
            return False
        if self.clock() < self.next_poll or self.lock.locked(): return False
        generation, revision = self.store.generation, self.store.revision
        if manual: self._check(revision, generation)
        async with self._operation():
            self.next_poll = self.clock() + 120
            try:
                adapter, key = await self._selected_adapter()
                sample = await adapter.read(key)
                self._check(revision, generation, owner=manual)
                if self.store.report(sample, revision=revision, generation=generation):
                    self._success()
                    self.service.publish('room.updated')
                return True
            except (PurifierUnavailable, ValueError) as exc:
                if not isinstance(exc, RoomAccessChanged): self._failed(exc, generation, revision)
                if manual: raise
                return False

    async def command(self, action, value, revision):
        return await self._command(action, value, revision)

    async def scene_command(self, action, value, revision, *, can_send):
        """Internal scene capability; never exposed as an HTTP bypass flag."""
        return await self._command(action, value, revision, scene_guard=can_send)

    async def _command(self, action, value, revision, *, scene_guard=None):
        generation = self.store.generation
        def check():
            self._check(revision, generation, owner=scene_guard is None)
            if scene_guard is not None and (scene_guard() is not True or self.store.override_active(self.utcnow())):
                raise RoomAccessChanged('Scene permission changed or a manual override is active.')
        check()
        self.store._action(action, value)
        async with self._operation():
            if self.clock() < self.next_command:
                raise PurifierRateLimit('Wait before sending another purifier command.')
            self.next_command = self.clock() + 3
            try:
                adapter, key = await self._selected_adapter()
            except PurifierUnavailable as exc:
                self._failed(exc, generation, revision)
                check()
                raise
            check()
            identifier = self.store.claim(action, value, revision=revision, generation=generation, now=self.utcnow(),
                                          kind='manual' if scene_guard is None else 'scene')
            def can_send():
                try:
                    check()
                    return self.store.selected is not None and self.store.selected['id'] == key
                except (ValueError, RoomAccessChanged): return False
            try:
                result = await adapter.command(key, action, value, can_send=can_send)
            except PurifierUnavailable as exc:
                self.store.finish(identifier, {'status': 'not_sent', 'accepted': False}, generation=generation, revision=revision)
                # A privacy/configuration change is not a provider outage. Return
                # its authorization error and don't poison the next selection.
                check()
                self._failed(exc, generation, revision)
                raise
            # On cancellation the durable unconfirmed receipt remains. No replay.
            self.store.finish(identifier, result, generation=generation, revision=revision)
            if result.get('reported'):
                self.store.report(result['reported'], generation=generation, revision=revision)
            if result['status'] != 'confirmed' and generation == self.store.generation and revision == self.store.revision:
                self.store.health = 'unconfirmed'
            if scene_guard is None: check()
            self.next_poll = self.clock() + 120
            self.service.publish('room.updated')
            return result

    async def run(self):
        while not self.closed:
            try: await self.refresh()
            except Exception: pass  # Fixed UI health only; never log provider data.
            await asyncio.sleep(15)

    async def close(self):
        self.closed = True
        async with self.lock:
            if self.adapter: await self.adapter.close()
            self.adapter = None
