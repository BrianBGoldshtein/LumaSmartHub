"""Disposable real HTTP/WebSocket fixture for fan setup; no USB is opened."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from fastapi import HTTPException, Request

from luma.api import create_app
from luma.ir_protocol import InfraredUnavailable, send_result
from test_fans import DEVICE, RAW


class FakeInfrared:
    def __init__(self):
        self.mode = 'normal'
        self.actions = []
        self.dispatches = 0
        self.cancellations = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()

    async def __call__(self, payload):
        action = payload['action']
        self.actions.append(action)
        if action == 'send':
            self.dispatches += 1
        if self.mode == 'unavailable':
            raise InfraredUnavailable('QA USB unavailable sentinel')
        if self.mode == 'raise':
            raise OSError('QA_SECRET_SENTINEL')
        if self.mode == 'block_learn' and action == 'learn':
            self.started.set()
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.cancellations += 1
                raise
        if action == 'discover':
            return {'devices': [DEVICE]}
        if action == 'learn':
            return {'signal': {**RAW, 'carrier_source': 'measured'}}
        return send_result('sent_unconfirmed')


async def main():
    with TemporaryDirectory(prefix='luma-fan-qa-') as directory:
        app = create_app(data_dir=directory,
                         frontend_dir=Path(__file__).resolve().parents[2] / 'frontend' / 'dist')
        service = app.state.luma
        service.update_settings({'voice_enabled': False, 'theme': 'hearth'})
        infrared = FakeInfrared()
        app.state.fan_runtime.transport = infrared

        def qa_loopback(request):
            if (not request.client or request.client.host not in ('127.0.0.1', '::1')
                    or request.headers.get('origin') not in (None, 'http://127.0.0.1:8752')):
                raise HTTPException(403)

        @app.post('/_qa/control')
        async def control(request: Request):
            qa_loopback(request)
            body = await request.json()
            mode = body.get('mode', 'normal')
            if mode not in ('normal', 'unavailable', 'raise', 'block_learn'):
                raise HTTPException(422)
            infrared.mode = mode
            if mode == 'block_learn':
                infrared.started.clear()
                infrared.release.clear()
            if body.get('release') is True:
                infrared.release.set()
            return status_value()

        @app.get('/_qa/status')
        async def status(request: Request):
            qa_loopback(request)
            return status_value()

        def status_value():
            # No wire payloads, signal durations or transport exception text.
            return {'fixture': 'synthetic-fans', 'mode': infrared.mode,
                    'actions': list(infrared.actions), 'dispatches': infrared.dispatches,
                    'cancellations': infrared.cancellations,
                    'learn_started': infrared.started.is_set()}

        # The static frontend fallback is appended by create_app; keep the
        # fixture-only diagnostic routes ahead of it.
        qa_routes = [route for route in app.router.routes
                     if getattr(route, 'path', '').startswith('/_qa/')]
        app.router.routes[:] = [route for route in app.router.routes if route not in qa_routes]
        fallback = next((index for index, route in enumerate(app.router.routes)
                         if getattr(route, 'path', '') == '/{path:path}'), len(app.router.routes))
        app.router.routes[fallback:fallback] = qa_routes

        @asynccontextmanager
        async def lifespan(_):
            try:
                yield
            finally:
                await app.state.fan_runtime.close()
                await app.state.room_runtime.close()
                app.state.transit_runtime.close()
                app.state.weather.client.client.close()

        app.router.lifespan_context = lifespan
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8752, log_level='warning'))

        async def deadline():
            await asyncio.sleep(1200)
            server.should_exit = True

        timeout = asyncio.create_task(deadline())
        print('Synthetic fan QA: http://127.0.0.1:8752/?setup=extras. Temporary data; fake IR transport only; 20-minute limit.', flush=True)
        try:
            await server.serve()
        finally:
            timeout.cancel()


if __name__ == '__main__':
    asyncio.run(main())
