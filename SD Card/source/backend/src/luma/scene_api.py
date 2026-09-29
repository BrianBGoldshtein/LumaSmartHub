"""Local-owner scene editor/run API. No arbitrary trigger or remote bypass."""
import asyncio
import json
from contextlib import suppress
from typing import Literal

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr

from .room_api import Revision, _unique_pairs
from .scene_runtime import SceneRuntime


SceneKey = Literal['morning', 'night', 'arrive', 'away']


class Action(BaseModel):
    model_config = {'extra': 'forbid'}
    device: Literal['purifier', 'fan_1', 'fan_2']
    action: str = Field(min_length=1, max_length=32)
    value: StrictBool | StrictInt | StrictStr | None
    binding: str = Field(pattern=r'^[a-f0-9]{64}$')


class Edit(Revision):
    enabled: StrictBool
    automatic: StrictBool
    actions: list[Action] = Field(max_length=8)


class RemoteEdit(Revision):
    model_config = {'extra': 'forbid'}
    enabled: StrictBool
    scenes: list[SceneKey] = Field(max_length=4)


class RemoteReset(Revision):
    model_config = {'extra': 'forbid'}
    confirmed: StrictBool


def install_scene_api(app, service, local_only, bluetooth):
    runtime = SceneRuntime(service, app.state.room_runtime, app.state.fan_runtime, bluetooth)
    app.state.scene_runtime = runtime

    def owner():
        if not runtime.owner_allowed(): raise HTTPException(403, 'Unlock Luma to configure or run scenes.')

    def response(value=None):
        return JSONResponse(value if value is not None else runtime.configuration(), headers={'Cache-Control': 'no-store'})

    def failure(exc):
        if isinstance(exc, PermissionError): return HTTPException(403, str(exc))
        if isinstance(exc, ValueError): return HTTPException(409, str(exc))
        return HTTPException(503, 'Scene could not finish. Review its results; it will not be retried.')

    async def body(request, model, limit):
        raw = bytearray()
        try:
            async with asyncio.timeout(3):
                async for chunk in request.stream():
                    if len(raw) + len(chunk) > limit: raise ValueError()
                    raw.extend(chunk)
            return model.model_validate(json.loads(raw, object_pairs_hook=_unique_pairs))
        except (ValueError, TypeError, TimeoutError):
            raise HTTPException(422, 'Use the scene editor to submit bounded scene settings.') from None
        finally: raw.clear()

    @app.get('/api/v1/scenes', dependencies=[Depends(local_only)])
    async def configuration():
        owner()
        return response()

    @app.post('/api/v1/scenes/cancel', dependencies=[Depends(local_only)])
    async def cancel():
        owner()
        await runtime.cancel()
        return response()

    @app.put('/api/v1/scenes/remote', dependencies=[Depends(local_only)])
    async def remote_permissions(request: Request):
        owner()
        payload = await body(request, RemoteEdit, 2048)
        try: runtime.save_remote(enabled=payload.enabled, scenes=payload.scenes, revision=payload.revision)
        except Exception as exc: raise failure(exc) from None
        owner()
        return response()

    @app.post('/api/v1/scenes/remote/reset', dependencies=[Depends(local_only)])
    async def reset_remote_permissions(request: Request):
        owner()
        payload = await body(request, RemoteReset, 1024)
        try: runtime.reset_remote_recovery(revision=payload.revision, confirmed=payload.confirmed)
        except Exception as exc: raise failure(exc) from None
        owner()
        return response()

    @app.put('/api/v1/scenes/{key}', dependencies=[Depends(local_only)])
    async def edit(key: SceneKey, request: Request):
        owner()
        payload = await body(request, Edit, 8192)
        try: runtime.edit(key, payload.model_dump(exclude={'revision'}), payload.revision)
        except Exception as exc: raise failure(exc) from None
        owner()
        return response()

    @app.post('/api/v1/scenes/{key}/run', dependencies=[Depends(local_only)])
    async def run(key: SceneKey, request: Request):
        owner()
        payload = await body(request, Revision, 512)
        job = asyncio.create_task(runtime.manual(key, payload.revision))
        try:
            while True:
                done, _ = await asyncio.wait({job}, timeout=.1)
                if await request.is_disconnected():
                    raise ValueError('Scene control connection closed. Review results before running another scene.')
                if done:
                    result = job.result()
                    break
            owner()
            return response({'result': result, 'configuration': runtime.configuration()})
        except asyncio.CancelledError:
            raise HTTPException(409, 'Scene cancelled. Already-sent actions may have taken effect.') from None
        except HTTPException: raise
        except Exception as exc: raise failure(exc) from None
        finally:
            if not job.done(): job.cancel()
            with suppress(asyncio.CancelledError, Exception): await job

    return runtime
