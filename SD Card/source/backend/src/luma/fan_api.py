"""Primary-owner cooling preferences; hardware remains in the USB broker."""
import asyncio
from contextlib import suppress
from typing import Literal

from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .backup_broker import backup_request
from .admin_authority import require_request_admin

PREFERENCES = 'usb_fan_v1'


class FanCommand(BaseModel):
    model_config = {'extra': 'forbid'}
    action: Literal['always_on', 'automatic', 'probe', 'confirm']
    acknowledged: bool = Field(default=False, strict=True)


class FanRuntime:
    def __init__(self, storage, request=backup_request, *, connected=lambda:False, service=None):
        self.storage, self.request, self.lock = storage, request, asyncio.Lock()
        self.connected, self.service = connected, service
        self.standby = None

    def standby_override(self):
        try:
            return not bool(self.connected())
        except Exception:
            # Unknown presence must never strand the owner without a mouse.
            return True

    async def _apply(self, preferences, operation='poll', acknowledged=False):
        standby = self.standby_override()
        wire_operation = ('keep_on' if self.standby is not True or operation=='keep_on' else 'poll') if standby else operation
        result = await self.request({'action':'fan','operation':wire_operation,
            **preferences,'mode':'always_on' if standby else preferences['mode'],
            'acknowledged':acknowledged})
        if not standby and self.standby_override():
            # A disconnect racing an in-flight automatic request wins before
            # returning status; never leave a stale off decision in effect.
            standby = True
            result = await self.request({'action':'fan','operation':'keep_on',
                **preferences,'mode':'always_on','acknowledged':False})
        if result.get('fault') is True:
            # A broker restart/update must not revive a qualification from
            # before a real switching fault. Only an acknowledged new probe
            # and explicit physical observation may re-enable automatic off.
            preferences = {'mode':'always_on','qualified_topology':None}
            if self.preferences() != preferences:
                self.storage.set_cache('device', PREFERENCES, preferences)
        self.standby = standby
        result = {**result,'standby_override':standby}
        if standby:
            # Selected mode is retained; the broker's effective mode is on.
            result['mode'] = preferences['mode']
            if result.get('available') and result.get('usb_power')=='on':
                result['reason'] = 'Standby · no connected phones · mouse USB power stays on'
        return result

    def preferences(self):
        saved = self.storage.get_cache('device', PREFERENCES) or {}
        if not isinstance(saved, dict):
            saved = {}
        mode = saved.get('mode', 'always_on')
        qualified = saved.get('qualified_topology')
        import re
        if not isinstance(mode, str) or mode not in {'automatic', 'always_on'}:
            mode = 'always_on'
        if not isinstance(qualified, str) or not re.fullmatch(r'[a-f0-9]{64}', qualified):
            qualified = None
        return {'mode': mode, 'qualified_topology': qualified}

    async def poll(self):
        async with self.lock:
            return await self._apply(self.preferences())

    async def command(self, command):
        async with self.lock:
            require_request_admin()
            preferences = self.preferences()
            action = command.action
            if action in {'probe', 'confirm'} and not command.acknowledged:
                raise HTTPException(422, 'Confirm the USB interruption and fan observation first.')
            if action in {'probe','confirm'} and self.standby_override():
                raise HTTPException(409, 'Connect a registered phone before testing USB power. Standby keeps the mouse powered.')
            if action == 'probe':
                preferences = {'mode': 'always_on', 'qualified_topology': None}
                # A crash during testing must not resurrect automatic mode.
                self.storage.set_cache('device', PREFERENCES, preferences)
            if action in {'always_on', 'automatic'}:
                preferences['mode'] = action
            result = await self._apply(preferences,
                'keep_on' if action == 'always_on' else action if action in {'probe','confirm'} else 'poll',
                command.acknowledged)
            require_request_admin()
            if action == 'automatic' and not result.get('qualified'):
                raise HTTPException(409, 'Run and confirm the USB fan test before enabling automatic cooling.')
            if action == 'confirm':
                preferences['qualified_topology'] = result['qualified_topology']
            self.storage.set_cache('device', PREFERENCES, preferences)
            return result

    async def run(self):
        queue = self.service.subscribe() if self.service else None
        try:
            while True:
                with suppress(ValueError, OSError):
                    await self.poll()
                if queue is None:
                    await asyncio.sleep(5)
                else:
                    try:
                        async with asyncio.timeout(5):
                            while (await queue.get()).get('type') not in {
                                'presence.updated','user.presence.updated','users.updated'}:
                                pass
                    except TimeoutError:
                        pass
        finally:
            if queue is not None:
                self.service.unsubscribe(queue)
            # The root watchdog independently restores on missing heartbeat.
            with suppress(ValueError, OSError, TimeoutError):
                await asyncio.wait_for(self.request({'action': 'fan', 'operation': 'keep_on',
                    **self.preferences(), 'mode': 'always_on', 'acknowledged': False}), 4)


def install_fan_api(app, storage, local_only):
    runtime = FanRuntime(storage, connected=lambda:app.state.bluetooth.present_ids(), service=app.state.luma)
    app.state.fan = runtime

    @app.get('/api/v1/device/fan', dependencies=[Depends(local_only)])
    async def status():
        try:
            result = await runtime.poll()
        except (ValueError, OSError):
            raise HTTPException(503, 'Cooling controller unavailable. Keep the fan powered continuously.') from None
        return JSONResponse(result, headers={'Cache-Control': 'no-store'})

    @app.post('/api/v1/device/fan', dependencies=[Depends(local_only)])
    async def command(value: FanCommand):
        try:
            result = await runtime.command(value)
        except (ValueError, OSError):
            raise HTTPException(503, 'Cooling change unavailable. Remove USB drives and finish updates before testing.') from None
        return JSONResponse(result, headers={'Cache-Control': 'no-store'})
