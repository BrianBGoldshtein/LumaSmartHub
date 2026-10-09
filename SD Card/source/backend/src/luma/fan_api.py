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
    def __init__(self, storage, request=backup_request):
        self.storage, self.request, self.lock = storage, request, asyncio.Lock()

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
            return await self.request({'action': 'fan', 'operation': 'poll',
                                       **self.preferences(), 'acknowledged': False})

    async def command(self, command):
        async with self.lock:
            require_request_admin()
            preferences = self.preferences()
            action = command.action
            if action in {'probe', 'confirm'} and not command.acknowledged:
                raise HTTPException(422, 'Confirm the USB interruption and fan observation first.')
            if action == 'probe':
                preferences = {'mode': 'always_on', 'qualified_topology': None}
                # A crash during testing must not resurrect automatic mode.
                self.storage.set_cache('device', PREFERENCES, preferences)
            if action in {'always_on', 'automatic'}:
                preferences['mode'] = action
            result = await self.request({'action': 'fan',
                'operation': 'keep_on' if action == 'always_on' else action if action in {'probe', 'confirm'} else 'poll',
                **preferences, 'acknowledged': command.acknowledged})
            require_request_admin()
            if action == 'automatic' and not result.get('qualified'):
                raise HTTPException(409, 'Run and confirm the USB fan test before enabling automatic cooling.')
            if action == 'confirm':
                preferences['qualified_topology'] = result['qualified_topology']
            self.storage.set_cache('device', PREFERENCES, preferences)
            return result

    async def run(self):
        try:
            while True:
                with suppress(ValueError, OSError):
                    await self.poll()
                await asyncio.sleep(5)
        finally:
            # The root watchdog independently restores on missing heartbeat.
            with suppress(ValueError, OSError, TimeoutError):
                await asyncio.wait_for(self.request({'action': 'fan', 'operation': 'keep_on',
                    **self.preferences(), 'mode': 'always_on', 'acknowledged': False}), 4)


def install_fan_api(app, storage, local_only):
    runtime = FanRuntime(storage)
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
