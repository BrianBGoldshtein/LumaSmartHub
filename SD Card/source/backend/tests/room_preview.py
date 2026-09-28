"""Disposable real HTTP/WS/UI fixture; all VeSync traffic is synthetic."""
import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
import uvicorn
from fastapi import HTTPException, Request

from luma.api import create_app
from luma.purifier_adapter import PurifierAdapter
from test_purifier_adapter import Provider


async def main():
    with TemporaryDirectory(prefix='luma-room-qa-') as directory:
        app = create_app(data_dir=directory, frontend_dir=Path(__file__).resolve().parents[2] / 'frontend' / 'dist')
        service, runtime = app.state.luma, app.state.room_runtime
        service.update_settings({'voice_enabled': False, 'theme': 'hearth'})
        service.display_clock_trusted = lambda: True
        provider = Provider()
        runtime.factory = lambda saved=None, **kwargs: PurifierAdapter(saved, transport=httpx.MockTransport(provider), **kwargs)

        @app.post('/_qa/control')
        async def control(request: Request):
            if request.client.host not in ('127.0.0.1', '::1') or request.headers.get('origin') not in (None, 'http://127.0.0.1:8750'):
                raise HTTPException(403)
            body = await request.json()
            mode = body.get('mode', 'normal')
            if mode not in ('normal', 'offline', 'quota', 'unconfirmed', 'auth'): raise HTTPException(422)
            provider.fail = (lambda _: httpx.Response({'offline': 503, 'quota': 429, 'auth': 401}[mode])) if mode in ('offline', 'quota', 'auth') else None
            provider.adopt = mode != 'unconfirmed'
            if body.get('reset_slots'): runtime.next_setup = runtime.next_poll = runtime.next_command = 0
            if body.get('locked') is True:
                service.update_settings({'onboarding_completed': True})
                service.state.pin_unlocked_until = None
                service.phone_disconnected()
                service.publish('privacy.updated')
            elif body.get('locked') is False:
                service.unlock_with_pin()
            if body.get('theme') in ('hearth', 'luma-glass', 'neon-grid'):
                service.update_settings({'theme': body['theme']})
            return {'commands': provider.command_count, 'connected': service.room.session is not None, 'selected': service.room.selected is not None}

        async def tick():
            while True:
                service.tick()
                await asyncio.sleep(1)

        @asynccontextmanager
        async def lifespan(_):
            jobs = [asyncio.create_task(tick()), asyncio.create_task(runtime.run())]
            try: yield
            finally:
                for job in jobs: job.cancel()
                for job in jobs:
                    with suppress(asyncio.CancelledError): await job
                await runtime.close()
                app.state.transit_runtime.close()
                app.state.weather.client.client.close()
        app.router.lifespan_context = lifespan
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8750, log_level='warning'))
        async def deadline():
            await asyncio.sleep(1200)
            server.should_exit = True
        timeout = asyncio.create_task(deadline())
        print('Synthetic room QA: http://127.0.0.1:8750/?setup=extras. Temporary data, no accounts/hardware; 20-minute limit.', flush=True)
        try: await server.serve()
        finally: timeout.cancel()


if __name__ == '__main__': asyncio.run(main())
