"""Owner-local fan learning/control. No polling, automatic actions or retries."""
import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from time import monotonic

from .fans import SLOTS, slot_key, button_key
from .ir_broker import ir_request
from .ir_protocol import InfraredBusy, InfraredError, InfraredUnavailable, validate_result
from .ir_signal import carrier


class FanAccessChanged(InfraredError):
    pass


class FanCancelled(InfraredError):
    pass


class FanRuntime:
    def __init__(self, service, *, transport=ir_request, clock=monotonic, utcnow=None):
        self.service, self.store = service, service.fans
        self.transport, self.clock = transport, clock
        self.utcnow = utcnow or (lambda: datetime.now(UTC))
        self.lock = asyncio.Lock()
        self.catalog, self.catalog_at = [], None
        self.reviewed = set()  # No-serial route review is deliberately boot-local.
        self.io_task = None
        self.epoch = 0
        self.closed = False
        self.next_operation = 0

    def owner_allowed(self):
        return not self.closed and (not self.service.settings.onboarding_completed or not self.service.snapshot()['privacy_redacted'])

    def check(self, revision, generation, epoch=None, *, scene_guard=None):
        if (not self.owner_allowed() if scene_guard is None else self.closed or scene_guard() is not True):
            raise FanAccessChanged('Fan access or scene permission changed.')
        self.store.check(revision, generation)
        if epoch is not None and epoch != self.epoch: raise FanCancelled('Fan operation cancelled. No automatic retry.')

    @asynccontextmanager
    async def operation(self, revision, *, scene_guard=None):
        generation, epoch = self.store.generation, self.epoch
        self.check(revision, generation, epoch, scene_guard=scene_guard)
        if self.lock.locked() or self.clock() < self.next_operation:
            raise InfraredBusy('A fan operation is in progress or just finished. Nothing is queued.')
        async with self.lock:
            try: yield generation, epoch
            finally: self.next_operation = self.clock() + 1

    async def io(self, payload, revision, generation, epoch, *, scene_guard=None):
        self.check(revision, generation, epoch, scene_guard=scene_guard)
        task = asyncio.create_task(self.transport(payload))
        self.io_task = task
        try:
            async with asyncio.timeout(28):
                while True:
                    self.check(revision, generation, epoch, scene_guard=scene_guard)
                    done, _ = await asyncio.wait({task}, timeout=.1)
                    self.check(revision, generation, epoch, scene_guard=scene_guard)
                    if done:
                        result = validate_result(payload['action'], task.result())
                        if 'error' in result: raise InfraredError(result['error'])
                        return result
        except asyncio.CancelledError:
            if epoch != self.epoch and not self.closed:
                raise FanCancelled('Fan operation cancelled. No automatic retry.') from None
            raise
        finally:
            if not task.done(): task.cancel()
            with suppress(asyncio.CancelledError, Exception): await task
            if self.io_task is task: self.io_task = None

    def fresh_catalog(self):
        if self.catalog_at is None or not 0 <= self.clock() - self.catalog_at <= 300:
            raise ValueError('Discover USB adapters again before changing fan setup.')
        return self.catalog

    def device(self, identifier, capability):
        row = next((row for row in self.fresh_catalog() if row['id'] == identifier and row[capability]), None)
        if row is None: raise ValueError('Choose a compatible adapter from the discovered list.')
        return row

    async def discover(self, revision):
        async with self.operation(revision) as (generation, epoch):
            result = await self.io({'action': 'discover'}, revision, generation, epoch)
            self.catalog, self.catalog_at = result['devices'], self.clock()
            # A missing adapter revokes volatile no-serial routing review.
            present = {row['id'] for row in self.catalog}
            self.reviewed = {token for token in self.reviewed if token[1] in present}
            return result['devices']

    async def select(self, fan, identifier, emitter, name, revision):
        slot_key(fan)
        async with self.operation(revision) as (generation, epoch):
            self.check(revision, generation, epoch)
            device = self.device(identifier, 'send')
            self.store.select(fan, name, {'device': device, 'emitter': emitter}, revision=revision, generation=generation)
            self.reviewed = {token for token in self.reviewed if token[0] != fan}
            self.reviewed.add((fan, identifier, emitter))
            self.service.publish('fans.updated')

    async def review_output(self, fan, revision):
        slot_key(fan)
        async with self.operation(revision) as (generation, epoch):
            row = self.store.slots[fan]
            if not row: raise ValueError('Select the fan output first.')
            device = self.device(row['route']['device']['id'], 'send')
            if device != row['route']['device']: raise ValueError('Adapter capabilities changed. Select its output again.')
            self.reviewed.add((fan, device['id'], row['route']['emitter']))

    async def remove(self, fan, revision):
        slot_key(fan)
        generation = self.store.generation
        self.check(revision, generation)
        # Invalidate stored configuration before cancelling an in-flight capture.
        self.store.select(fan, None, None, revision=revision, generation=generation)
        self.reviewed = {token for token in self.reviewed if token[0] != fan}
        await self.cancel()
        self.service.publish('fans.updated')

    async def learn(self, fan, key, receiver, frequency, revision):
        slot_key(fan); button_key(key); carrier(frequency, optional=True)
        async with self.operation(revision) as (generation, epoch):
            if not self.store.slots[fan]: raise ValueError('Select this fan output first.')
            device = self.device(receiver, 'receive')
            if not device['measure_carrier'] and frequency is None:
                raise ValueError('Enter a documented remote carrier, or choose a carrier-measuring receiver.')
            result = await self.io({'action': 'learn', 'device_id': receiver, 'carrier_hz': frequency}, revision, generation, epoch)
            self.check(revision, generation, epoch)
            raw = {key: result['signal'][key] for key in ('carrier_hz', 'durations')}
            self.store.learned(fan, key, raw, revision=revision, generation=generation)
            self.service.publish('fans.updated')

    async def forget(self, fan, key, revision):
        async with self.operation(revision) as (generation, epoch):
            self.store.forget(fan, key, revision=revision, generation=generation)
            self.service.publish('fans.updated')

    async def command(self, fan, key, revision, *, test=False, confirmed=False):
        slot_key(fan); button_key(key)
        async with self.operation(revision) as (generation, epoch):
            kind = 'test' if test else 'manual'
            # Durable unknown receipt BEFORE any possible driver write. Cancel,
            # lost access, disk error after dispatch or restart never replays it.
            identifier, payload = self.store.claim(fan, key, kind=kind, confirmed=confirmed,
                                                   revision=revision, generation=generation, now=self.utcnow())
            try:
                result = await self.io(payload, revision, generation, epoch)
            except Exception:
                self.service.publish('fans.updated')
                raise  # Unknown stays durable, including uncertain broker errors.
            self.store.finish(fan, identifier, result['status'], revision=revision, generation=generation)
            self.check(revision, generation, epoch)
            self.service.publish('fans.updated')
            return {'id': identifier, **result}

    async def observe(self, fan, identifier, expected_state, other_unchanged, revision, *, repeat_same_state=False):
        async with self.operation(revision) as (generation, epoch):
            self.store.observe(fan, identifier, expected_state, other_unchanged,
                               revision=revision, generation=generation, now=self.utcnow(), repeat_same_state=repeat_same_state)
            self.service.publish('fans.updated')

    def scene_ready(self, fan, key):
        # Either fan's unreviewed no-serial route weakens the independence proof.
        if any(row['needs_output_review'] for row in self.configuration()['fans']):
            return False
        try:
            self.store.command(fan, key, kind='scene', confirmed=False, now=self.utcnow())
            return not self.closed
        except ValueError: return False

    async def scene_command(self, fan, key, revision, *, can_send):
        """Internal absolute-only scene path; no learning or raw HTTP input."""
        guard = lambda: can_send() is True and self.scene_ready(fan, key)
        async with self.operation(revision, scene_guard=guard) as (generation, epoch):
            identifier, payload = self.store.claim(fan, key, kind='scene', confirmed=False,
                                                   revision=revision, generation=generation, now=self.utcnow())
            result = await self.io(payload, revision, generation, epoch, scene_guard=guard)
            self.store.finish(fan, identifier, result['status'], revision=revision, generation=generation)
            self.service.publish('fans.updated')
            return result

    async def cancel(self):
        if not self.closed and not self.owner_allowed(): raise FanAccessChanged('Unlock Luma to cancel fan setup.')
        self.epoch += 1
        task = self.io_task
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError, Exception): await task

    async def close(self):
        self.closed = True
        await self.cancel()

    def configuration(self):
        result = self.store.configuration(self.utcnow())
        for row in result['fans']:
            output = row['route']
            row['needs_output_review'] = bool(output and not output['device']['serial_present']
                                             and (row['id'], output['device']['id'], output['emitter']) not in self.reviewed)
        result['busy'] = self.lock.locked()
        return result
