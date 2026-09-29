"""Bounded sequential scene runner with an injected device boundary.

The injected dispatch boundary requires a final can_send() check immediately
before device transmission, including after every asynchronous preflight. A
return is a factual outcome, never optimistic state.
"""
import asyncio
from datetime import UTC, datetime
from time import monotonic

from .scenes import OUTCOMES


class SceneStopped(ValueError):
    pass


class SceneExecutor:
    def __init__(self, store, *, dispatch, authorize, trusted, clock=monotonic, utcnow=None, publish=None):
        self.store, self.dispatch = store, dispatch
        self.authorize, self.trusted = authorize, trusted
        self.clock, self.utcnow = clock, utcnow or (lambda: datetime.now(UTC))
        self.publish = publish or (lambda: None)
        self.closed = False
        self.task = None
        self.dispatch_task = None
        self.epoch = 0

    def _notify(self):
        try: self.publish()
        except Exception: pass  # A UI subscriber cannot change command semantics.

    def _dispatch_done(self, task):
        if not task.cancelled(): task.exception()  # Consume late failures, no payload logging.
        if self.dispatch_task is task: self.dispatch_task = None

    def _allowed(self, trigger, revision, generation, epoch, deadline):
        return (not self.closed and epoch == self.epoch and not self.store.recovery_error
                and self.clock() < deadline and self.trusted() is True
                and generation == self.store.generation and revision == self.store.revision
                and self.authorize(trigger) is True)

    async def run(self, trigger, *, revision):
        if self.closed or self.task is not None:
            raise SceneStopped('A scene is running or the service is stopping. Nothing was queued.')
        generation, epoch = self.store.generation, self.epoch
        deadline = self.clock() + 120
        if not self._allowed(trigger, revision, generation, epoch, deadline):
            raise SceneStopped('This scene trigger is not authorized.')
        # Synchronous transaction before installing/running the first I/O task.
        run = self.store.claim(trigger.scene, trigger.source, trigger.occurrence,
                               revision=revision, now=self.utcnow(), observed_at=trigger.observed_at,
                               trusted=self.trusted(),
                               remote_authorized=trigger.source == 'remote' and self.authorize(trigger) is True)
        allowed = lambda: (self.store.active == run['id']
                           and self._allowed(trigger, revision, generation, epoch, deadline))
        self.task = asyncio.current_task()
        self._notify()
        completed = False
        try:
            async with asyncio.timeout(120):
                for index in range(len(run['steps'])):
                    if not allowed(): break
                    item = self.store.begin_step(run['id'], index, generation=generation)
                    # Device boundary must revalidate current binding/capability,
                    # 1h override and final authorization itself. No retries.
                    status = await self._dispatch(item, allowed)
                    self.store.finish_step(run['id'], index, status, generation=generation)
                    self._notify()
                else:
                    completed = allowed()
        finally:
            try:
                # Unknown dispatched and untouched not_started steps remain
                # distinguishable even on cancellation or failed storage.
                self.store.finish(run['id'], generation=generation, completed=completed)
            finally:
                self.task = None
                self._notify()
        return self.store.configuration()['runs'][-1]

    async def _dispatch(self, item, allowed):
        if not allowed(): return 'not_sent'
        task = asyncio.create_task(self.dispatch(item, can_send=allowed))
        self.dispatch_task = task
        task.add_done_callback(self._dispatch_done)
        try:
            async with asyncio.timeout(30):
                while True:
                    done, _ = await asyncio.wait({task}, timeout=.1)
                    if done:
                        status = task.result()
                        return status if status in OUTCOMES else 'unconfirmed'
                    if not allowed():
                        # It may already have sent; cancellation is not proof of
                        # failure. The durable unknown survives until recorded.
                        return 'unconfirmed'
        except asyncio.CancelledError:
            raise
        except Exception:
            return 'unconfirmed'
        finally:
            if not task.done(): task.cancel()
            try:
                done, _ = await asyncio.wait({task}, timeout=2)
            except asyncio.CancelledError:
                if not task.done(): self.closed = True
                raise
            if not done:
                # Misbehaving adapter cleanup must neither hang the app nor let
                # another scene race it. Keep its handle and fail closed until
                # service restart. Late can_send() now always returns false.
                self.closed = True

    async def cancel(self):
        self.epoch += 1
        task = self.task
        if task is not None and task is not asyncio.current_task():
            if not task.cancelling(): task.cancel()
            try: await asyncio.shield(task)
            except (asyncio.CancelledError, Exception): pass

    async def close(self):
        self.closed = True
        await self.cancel()
