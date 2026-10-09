"""Owner-local purifier setup and explicit nonqueued controls; no remote bypass."""
import asyncio
import json
from datetime import UTC, datetime
from typing import Literal

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr

from .purifier_adapter import PurifierBusy, PurifierRateLimit, PurifierReconnect, PurifierUnavailable
from .room_runtime import RoomAccessChanged, RoomRuntime
from .admin_authority import AdminDenied, require_request_admin


class Revision(BaseModel):
    model_config = {'extra': 'forbid'}
    revision: str = Field(pattern=r'^[a-f0-9-]{36}$')


class Selection(Revision):
    device_id: str | None = Field(default=None, pattern=r'^purifier-[a-f0-9]{24}$')
    name: str | None = Field(default=None, min_length=1, max_length=100)


class DeviceCommand(Revision):
    action: Literal['power', 'speed', 'mode', 'display']
    value: StrictBool | StrictInt | StrictStr


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError()
        result[key] = value
    return result


def install_room_api(app, service, local_only):
    runtime = RoomRuntime(service)
    app.state.room_runtime = runtime

    def owner():
        require_request_admin()
        if not runtime.owner_allowed():
            raise HTTPException(403, 'Unlock Luma to configure or control room devices.')

    def configuration():
        return JSONResponse(service.room.configuration(datetime.now(UTC)), headers={'Cache-Control': 'no-store'})

    async def operation(action):
        owner()
        try:
            result = await action()
        except RoomAccessChanged:
            raise HTTPException(403, 'Device access changed. Unlock Luma and reload.') from None
        except PurifierRateLimit as exc:
            raise HTTPException(429, str(exc)) from None
        except (PurifierBusy, PurifierReconnect, ValueError) as exc:
            raise HTTPException(409, str(exc)) from None
        except PurifierUnavailable as exc:
            raise HTTPException(502, str(exc)) from None
        except AdminDenied:
            raise
        except Exception:
            raise HTTPException(503, 'Room-device operation could not finish. Check the reported state before trying again.') from None
        owner()
        return result

    @app.get('/api/v1/room', dependencies=[Depends(local_only)])
    async def get_configuration():
        owner()
        return configuration()

    @app.post('/api/v1/room/vesync/login', dependencies=[Depends(local_only)])
    async def login(request: Request):
        owner()
        raw = bytearray()
        try:
            async with asyncio.timeout(3):
                async for chunk in request.stream():
                    if len(raw) + len(chunk) > 4096: raise ValueError()
                    raw.extend(chunk)
            body = json.loads(raw, object_pairs_hook=_unique_pairs)
            if not isinstance(body, dict) or set(body) != {'username', 'password', 'country', 'revision'}:
                raise ValueError()
            if any(not isinstance(body[key], str) for key in body): raise ValueError()
        except (ValueError, TypeError, TimeoutError):
            raise HTTPException(422, 'Enter VeSync credentials and account country on this hub.') from None
        finally:
            raw.clear()
        try:
            await operation(lambda: runtime.login(body['username'], body['password'], body['country'], body['revision']))
        finally:
            body.clear()
        return configuration()

    @app.post('/api/v1/room/vesync/disconnect', dependencies=[Depends(local_only)])
    async def disconnect(payload: Revision):
        await operation(lambda: runtime.disconnect(payload.revision))
        return configuration()

    @app.post('/api/v1/room/purifier/discover', dependencies=[Depends(local_only)])
    async def discover(payload: Revision):
        devices = await operation(lambda: runtime.discover(payload.revision))
        return JSONResponse({'devices': devices}, headers={'Cache-Control': 'no-store'})

    @app.post('/api/v1/room/purifier/select', dependencies=[Depends(local_only)])
    async def select(payload: Selection):
        await operation(lambda: runtime.select(payload.device_id, payload.name, payload.revision))
        return configuration()

    @app.post('/api/v1/room/purifier/refresh', dependencies=[Depends(local_only)])
    async def refresh():
        if not await operation(lambda: runtime.refresh(manual=True)):
            raise HTTPException(429, 'Purifier is unconfigured, resting, or recently checked. Saved settings are unchanged.')
        return configuration()

    @app.post('/api/v1/room/purifier/command', dependencies=[Depends(local_only)])
    async def command(payload: DeviceCommand):
        result = await operation(lambda: runtime.command(payload.action, payload.value, payload.revision))
        return JSONResponse({'result': result, 'configuration': service.room.configuration(datetime.now(UTC))}, headers={'Cache-Control': 'no-store'})

    return runtime
