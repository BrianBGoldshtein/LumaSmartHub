"""Independent ANCS workers, coordinated radio and primary-only notifications.

This uses actual BlueZ sessions, not pretend presence or connection rotation.
The application must install per-user privacy projections before enabling it.
"""
from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
import sys

from .ancs_advertising import ANCSReconnectAdvertising
from .bluetooth_runtime import BluetoothRuntime
from .companion_auth import PhonePresence
from .profiles import PRIMARY_ID, ProfileError, ProfileRepository
from .radio_scheduler import RadioScheduler


class UserBluetoothService:
    """A radio worker cannot update another user's presence or notifications."""
    def __init__(self, service, profiles, uid):
        self.service, self.profiles, self.id = service, profiles, uid
        self.state = SimpleNamespace(phone_connected=False, phone_last_seen_at=None)
        self.scenes = SimpleNamespace(definitions={})

    @property
    def settings(self):
        user = self.profiles.get(self.id)
        return replace(self.service.settings, phone_address=user.phone_address)

    def phone_seen(self, now=None):
        changed = not self.state.phone_connected
        self.state.phone_connected = True
        self.state.phone_last_seen_at = now or datetime.now(UTC)
        if changed:
            self.service.publish('user.presence.updated', {'profile_id': self.id, 'connected': True})

    def phone_disconnected(self, now=None):
        changed = self.state.phone_connected
        self.state.phone_connected = False
        self.state.phone_last_seen_at = None
        if changed:
            self.service.publish('user.presence.updated', {'profile_id': self.id, 'connected': False})

    def receive_notification(self, notice):
        # Secondary call/message content is outside 0.3.1's shared-wall scope.
        # Subscribe only for authorization, never mix their notifications into
        # the primary user's existing notification queue.
        return False

    def remove_notification(self, notification_id):
        return None


class MultiPhoneBluetooth:
    def __init__(self, service, profiles: ProfileRepository, *, coordinator=None):
        self.service, self.profiles = service, profiles
        self.coordinator = coordinator or RadioScheduler()
        self.children = {PRIMARY_ID: BluetoothRuntime(service, coordinator=self.coordinator)}
        self.advertiser = ANCSReconnectAdvertising(self.registered_addresses)

    def __getattr__(self, name):
        # Existing primary diagnostics/scene hooks remain compatible. Never
        # treat this primary view as permission to read a secondary's data.
        return getattr(self.children[PRIMARY_ID], name)

    @property
    def status(self):
        return self.children[PRIMARY_ID].status

    @status.setter
    def status(self, value):
        self.children[PRIMARY_ID].status = value

    @property
    def scene_authorized(self):
        return self.children[PRIMARY_ID].scene_authorized

    @scene_authorized.setter
    def scene_authorized(self, value):
        self.children[PRIMARY_ID].scene_authorized = value

    def registered_addresses(self):
        return tuple(user.phone_address for user in self.profiles.list() if user.phone_address)

    def runtime(self, uid):
        self.profiles.get(uid)
        if uid not in self.children:
            facade = UserBluetoothService(self.service, self.profiles, uid)
            self.children[uid] = BluetoothRuntime(facade, coordinator=self.coordinator, profile_id=uid)
        return self.children[uid]

    def companion_presence(self, uid=PRIMARY_ID):
        try:
            user = self.profiles.get(uid)
            child = self.children.get(uid)
            if child is None:
                return PhonePresence(user.phone_address or '', False, '')
            return child.remote_authorized.snapshot(user.phone_address,
                phone_connected=child.service.state.phone_connected)
        except ProfileError:
            return PhonePresence('', False, '')

    def present_ids(self, *, wall=False):
        return {user.id for user in self.profiles.list()
                if (not wall or user.wall_share_approved) and self.companion_presence(user.id).authorized}

    @property
    def advertising_status(self):
        return self.advertiser.status

    async def reconnect_advertising_worker(self):
        await self.advertiser.run()

    async def session(self, address):
        # Preserve primary qualification entrypoint; supervisor uses each
        # child's session directly through its independent run worker.
        await self.children[PRIMARY_ID].session(address)

    async def scene_presence_worker(self):
        await self.children[PRIMARY_ID].scene_presence_worker()

    async def run(self, *, pause=asyncio.sleep):
        if sys.platform != 'linux':
            self.children[PRIMARY_ID].status = 'Requires Linux BlueZ'
            return
        tasks = {}
        try:
            while True:
                wanted = {user.id for user in self.profiles.list() if user.phone_address}
                for uid in set(tasks) - wanted:
                    task = tasks.pop(uid)
                    task.cancel()
                    with suppress(asyncio.CancelledError, ProfileError):
                        await task
                    child = self.children.get(uid)
                    if child:
                        child.remote_authorized.clear()
                        child.service.phone_disconnected()
                    if uid != PRIMARY_ID:
                        self.children.pop(uid, None)
                    self.coordinator.forget(uid)
                for uid in wanted:
                    if uid not in tasks or tasks[uid].done():
                        if uid in tasks:
                            with suppress(Exception):
                                tasks[uid].result()
                        tasks[uid] = asyncio.create_task(self.runtime(uid).run(), name=f'luma-phone-{uid}')
                await pause(1)
        finally:
            for task in tasks.values():
                task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)
            for child in self.children.values():
                child.remote_authorized.clear()
                child.service.phone_disconnected()
