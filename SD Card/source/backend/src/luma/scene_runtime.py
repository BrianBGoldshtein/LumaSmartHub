"""Explicit local scenes and opt-in fresh calendar/authenticated-presence edges."""
import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from time import monotonic
from uuid import uuid4

from .scene_devices import SceneDevices, digest
from .scene_remote import RemoteScenePolicy
from .scene_executor import SceneExecutor
from .scene_triggers import PresenceTriggers, CalendarTriggers, SceneTrigger
from .scenes import AUTOMATIC, definition


def sleep_interval(service, now):
    ids, title = set(service.settings.sleep_calendar_ids), service.settings.sleep_event_title.strip().casefold()
    intervals = sorted((item.start.astimezone(UTC), item.end.astimezone(UTC)) for item in service.events
                       if item.calendar_id in ids and item.summary.strip().casefold() == title
                       and item.status != 'cancelled' and not item.all_day and not item.self_declined
                       and item.end.astimezone(UTC) > item.start.astimezone(UTC))
    merged = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]: merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else: merged.append((start, end))
    return next((item for item in merged if item[0] <= now < item[1]), None)


class SceneRuntime:
    def __init__(self, service, room, bluetooth, *, clock=monotonic, utcnow=None):
        self.service, self.store, self.bluetooth = service, service.scenes, bluetooth
        self.remote_policy = RemoteScenePolicy(service.scenes.storage)
        self.clock, self.utcnow = clock, utcnow or (lambda: datetime.now(UTC))
        self.devices = SceneDevices(service, room, utcnow=self.utcnow)
        self.presence, self.calendar = PresenceTriggers(), CalendarTriggers()
        self.trigger = None
        self.job = None
        self.closed = False
        self.observed_revision = None
        self.executor = SceneExecutor(self.store, dispatch=self.devices.dispatch, authorize=self.authorize,
                                      trusted=self.trusted, clock=clock, utcnow=self.utcnow,
                                      publish=lambda: service.publish('scenes.updated'))

    def trusted(self):
        try: return self.service.display_clock_trusted() is True
        except OSError: return False

    def owner_allowed(self):
        return not self.closed and (not self.service.settings.onboarding_completed or not self.service.snapshot()['privacy_redacted'])

    def calendar_fresh(self):
        at = self.service.calendar_synced_at
        return bool(self.service.settings.sleep_calendar_ids and at and not self.service.calendar_sync_error
                    and timedelta(0) <= self.utcnow() - at <= timedelta(minutes=10))

    def authorize(self, trigger):
        if self.closed: return False
        if trigger.source == 'manual': return self.owner_allowed()
        if trigger.source == 'remote':
            row = self.store.definitions[trigger.scene]
            return self.trusted() and self.remote_policy.effective(trigger.scene, row)
        if self.trigger is not trigger or not self.service.settings.onboarding_completed: return False
        row = self.store.definitions[trigger.scene]
        if not row['enabled'] or not row['automatic'] or AUTOMATIC[trigger.scene] != trigger.source: return False
        if trigger.source == 'presence':
            current = self.bluetooth.scene_presence.read(self.service.settings.phone_address)
            return current is (trigger.scene == 'arrive')
        return self.calendar_fresh() and (sleep_interval(self.service, self.utcnow()) is not None) == (trigger.scene == 'night')

    def configuration(self):
        result = self.store.configuration()
        result['devices'] = self.devices.catalog()
        result['clock_trusted'] = self.trusted()
        result['calendar_ready'] = self.calendar_fresh()
        result['phone_configured'] = bool(self.service.settings.phone_address)
        for row in result['definitions'].values():
            row['needs_review'] = any(item['binding'] != self.devices.binding(item['device']) for item in row['actions'])
        result['remote'] = self.remote_policy.configuration(result['definitions'])
        return result

    def save_remote(self, *, enabled, scenes, revision):
        if not self.owner_allowed(): raise PermissionError('Unlock Luma to change remote scene permissions.')
        if self.store.recovery_error: raise ValueError('Scene settings need recovery. Nothing was overwritten.')
        self.remote_policy.save(enabled, scenes, revision=revision,
                                definitions=self.store.definitions, devices=self.devices)
        self.service.publish('scenes.remote.updated')

    def reset_remote_recovery(self, *, revision, confirmed):
        if not self.owner_allowed(): raise PermissionError('Unlock Luma to recover remote scene permissions.')
        self.remote_policy.reset_corrupt(revision=revision, confirmed=confirmed)
        self.service.publish('scenes.remote.updated')

    async def remote(self, key):
        row = self.store.definitions[key]
        if not self.trusted() or not self.remote_policy.effective(key, row):
            raise PermissionError('This exact scene is not enabled for private remote control.')
        event = SceneTrigger(key, 'remote', str(uuid4()), self.utcnow())
        return await self.executor.run(event, revision=self.store.revision)

    def edit(self, key, config, revision):
        if not self.owner_allowed(): raise PermissionError('Unlock Luma to configure scenes.')
        clean = definition(config)
        # Disabling remains possible when devices are offline or removed. Only
        # enabling/changing live actions requires current reviewed capabilities.
        if clean['enabled']: clean['actions'] = self.devices.bind(clean['actions'])
        self.store.edit(key, clean, revision=revision)
        self.service.publish('scenes.updated')

    async def manual(self, key, revision):
        if not self.owner_allowed(): raise PermissionError('Unlock Luma to run scenes.')
        event = SceneTrigger(key, 'manual', str(uuid4()), self.utcnow())
        return await self.executor.run(event, revision=revision)

    async def cancel(self):
        if not self.owner_allowed(): raise PermissionError('Unlock Luma to cancel scenes.')
        pending = self.job
        await self.executor.cancel()
        # A manually requested run is acknowledged before dispatch so the
        # offline voice client can respond quickly. Also cancel the narrow
        # pre-claim window where the task was queued but the executor has not
        # yet installed its active-task guard.
        if pending is not None and pending is not asyncio.current_task() and not pending.done() and self.executor.task is None:
            pending.cancel()
            with suppress(asyncio.CancelledError, Exception): await pending

    def poll(self):
        now, ticks, trusted = self.utcnow(), self.clock(), self.trusted()
        if self.closed or not self.service.settings.onboarding_completed or self.store.recovery_error:
            self.presence.reset(); self.calendar.reset()
            return
        if self.observed_revision != self.store.revision:
            self.presence.reset(); self.calendar.reset()
            self.observed_revision = self.store.revision
        events = []
        if any(self.store.definitions[key]['automatic'] for key in ('arrive', 'away')):
            identity = self.service.settings.phone_address
            events.append(self.presence.observe(self.bluetooth.scene_presence.read(identity), identity=identity,
                                                monotonic=ticks, now=now, trusted=trusted))
        else: self.presence.reset()
        if any(self.store.definitions[key]['automatic'] for key in ('morning', 'night')):
            revision = digest([self.service.settings.sleep_calendar_ids, self.service.settings.sleep_event_title])
            events.append(self.calendar.observe(sleep_interval(self.service, now), revision=revision,
                                                monotonic=ticks, now=now, trusted=trusted, fresh=self.calendar_fresh()))
        else: self.calendar.reset()
        for event in events:
            if event is None: continue
            row = self.store.definitions[event.scene]
            # Consume edges even when disabled or busy. No delayed event queue.
            if not row['enabled'] or not row['automatic'] or self.executor.task or self.job and not self.job.done(): continue
            self.trigger = event
            self.job = asyncio.create_task(self._automatic(event, self.store.revision))

    async def _automatic(self, event, revision):
        try: await self.executor.run(event, revision=revision)
        except (ValueError, OSError): pass  # Disabled/cooldown/storage failure: never replay.
        finally:
            if self.trigger is event: self.trigger = None

    async def run(self):
        try:
            while not self.closed:
                try: self.poll()
                except Exception:
                    self.presence.reset(); self.calendar.reset()
                await asyncio.sleep(1)
        finally: await self.close()

    async def close(self):
        self.closed = True
        await self.executor.close()
        if self.job and self.job is not asyncio.current_task():
            if not self.job.done(): self.job.cancel()
            with suppress(asyncio.CancelledError, Exception): await self.job
