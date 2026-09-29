"""Fan setup is local-owner-only; raw IR is never accepted from HTTP clients."""
import asyncio
from contextlib import suppress
from typing import Literal

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import Field, StrictBool, StrictInt

from .fan_runtime import FanAccessChanged, FanCancelled, FanRuntime
from .ir_protocol import InfraredBusy, InfraredError, InfraredUnavailable
from .room_api import Revision


class Fan(Revision):
    fan: Literal['fan_1', 'fan_2']


class Selection(Fan):
    device_id: str = Field(pattern=r'^usb-ir-[a-f0-9]{24}$')
    emitter: StrictInt | None = Field(default=None, ge=1, le=32)
    name: str = Field(min_length=1, max_length=40)


class Button(Fan):
    button: str = Field(min_length=1, max_length=32)


class Learn(Button):
    receiver_id: str = Field(pattern=r'^usb-ir-[a-f0-9]{24}$')
    carrier_hz: StrictInt | None = Field(default=None, ge=20000, le=60000)


class Command(Button):
    confirmed: StrictBool = False


class Observation(Fan):
    command_id: str = Field(pattern=r'^[a-f0-9-]{36}$')
    expected_state: StrictBool
    other_unchanged: StrictBool
    repeat_same_state: StrictBool = False


def install_fan_api(app, service, local_only):
    runtime = FanRuntime(service)
    app.state.fan_runtime = runtime

    def owner():
        if not runtime.owner_allowed(): raise HTTPException(403, 'Unlock Luma to set up or control fans.')

    def response(value=None):
        return JSONResponse(runtime.configuration() if value is None else value, headers={'Cache-Control': 'no-store'})

    async def operation(action, request=None):
        owner()
        job = None
        try:
            if request is None:
                result = await action()
            else:
                # ASGI does not necessarily cancel work when an HTTP client
                # disconnects. Revoke the transport lease explicitly instead of
                # saving a late recording after the owner leaves the wizard.
                job = asyncio.create_task(action())
                while True:
                    done, _ = await asyncio.wait({job}, timeout=.1)
                    if await request.is_disconnected():
                        raise FanCancelled('Fan setup connection closed. Nothing will be retried.')
                    if done:
                        result = job.result()
                        break
        except FanAccessChanged:
            raise HTTPException(403, 'Fan access changed. Unlock Luma and reload.') from None
        except InfraredBusy as exc:
            raise HTTPException(429, str(exc)) from None
        except InfraredUnavailable:
            raise HTTPException(503, 'USB infrared is unavailable. No command will be retried automatically.') from None
        except (FanCancelled, InfraredError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from None
        except Exception:
            raise HTTPException(503, 'Fan operation could not finish. Check both fans before sending another command.') from None
        finally:
            if job is not None:
                if not job.done(): job.cancel()
                with suppress(asyncio.CancelledError, Exception): await job
        owner()
        return result

    @app.get('/api/v1/fans', dependencies=[Depends(local_only)])
    async def configuration():
        owner()
        return response()

    @app.post('/api/v1/fans/discover', dependencies=[Depends(local_only)])
    async def discover(payload: Revision, request: Request):
        devices = await operation(lambda: runtime.discover(payload.revision), request)
        return response({'devices': devices})

    @app.post('/api/v1/fans/select', dependencies=[Depends(local_only)])
    async def select(payload: Selection):
        await operation(lambda: runtime.select(payload.fan, payload.device_id, payload.emitter, payload.name, payload.revision))
        return response()

    @app.post('/api/v1/fans/review-output', dependencies=[Depends(local_only)])
    async def review_output(payload: Fan):
        await operation(lambda: runtime.review_output(payload.fan, payload.revision))
        return response()

    @app.post('/api/v1/fans/remove', dependencies=[Depends(local_only)])
    async def remove(payload: Fan):
        await operation(lambda: runtime.remove(payload.fan, payload.revision))
        return response()

    @app.post('/api/v1/fans/learn', dependencies=[Depends(local_only)])
    async def learn(payload: Learn, request: Request):
        await operation(lambda: runtime.learn(payload.fan, payload.button, payload.receiver_id, payload.carrier_hz, payload.revision), request)
        return response()

    @app.post('/api/v1/fans/forget', dependencies=[Depends(local_only)])
    async def forget(payload: Button):
        await operation(lambda: runtime.forget(payload.fan, payload.button, payload.revision))
        return response()

    @app.post('/api/v1/fans/test', dependencies=[Depends(local_only)])
    async def test(payload: Command, request: Request):
        result = await operation(lambda: runtime.command(payload.fan, payload.button, payload.revision, test=True, confirmed=payload.confirmed), request)
        return response({'result': result, 'configuration': runtime.configuration()})

    @app.post('/api/v1/fans/command', dependencies=[Depends(local_only)])
    async def command(payload: Command, request: Request):
        result = await operation(lambda: runtime.command(payload.fan, payload.button, payload.revision, confirmed=payload.confirmed), request)
        return response({'result': result, 'configuration': runtime.configuration()})

    @app.post('/api/v1/fans/observe', dependencies=[Depends(local_only)])
    async def observe(payload: Observation):
        await operation(lambda: runtime.observe(payload.fan, payload.command_id, payload.expected_state, payload.other_unchanged, payload.revision,
                                                repeat_same_state=payload.repeat_same_state))
        return response()

    @app.post('/api/v1/fans/cancel', dependencies=[Depends(local_only)])
    async def cancel():
        await operation(runtime.cancel)
        return response()

    return runtime
