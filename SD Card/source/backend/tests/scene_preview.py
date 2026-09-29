"""Disposable HTTP/WebSocket fixture for real scene editor integration checks.

All fan identities, IR observations and command outcomes are synthetic. No
USB device, account, campus network or physical appliance is contacted.
"""
import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from fastapi import HTTPException, Request

from luma.api import create_app
from luma.scene_remote import RemoteScenePolicy
from luma.scenes import Scenes
from test_fans import RAW, observed, configure


async def main():
    with TemporaryDirectory(prefix='luma-scene-qa-') as directory:
        frontend = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
        app = create_app(data_dir=directory, frontend_dir=frontend)
        service = app.state.luma
        service.update_settings({'voice_enabled': False, 'theme': 'hearth'})
        service.display_clock_trusted = lambda: True
        scenes = app.state.scene_runtime
        scenes.trusted = lambda: True

        # Populate production scene-capability checks with a fake, fully
        # observed two-output fan remote. Nothing is transmitted.
        configure(service.fans)
        for fan in ('fan_1', 'fan_2'):
            observed(service.fans, fan=fan)
            observed(service.fans, fan=fan, now=observed_time(1))
            service.fans.learned(fan, 'power_on', RAW, revision=service.fans.revision,
                                 generation=service.fans.generation)
            observed(service.fans, fan=fan, key='power_on', now=observed_time(2))
            observed(service.fans, fan=fan, key='power_on', now=observed_time(3))
        # Synthetic verification calls deliberately create a manual override;
        # clear that test-only state before scene execution.
        service.fans._save(overrides=dict.fromkeys(('fan_1', 'fan_2')))

        commands = []
        dispatch_gate = asyncio.Event()
        dispatch_gate.set()

        async def synthetic_scene_command(fan, key, revision, *, can_send):
            if can_send() is not True:
                return {'status': 'not_sent'}
            commands.append((fan, key))
            # Hold a disposable, already-dispatched result so the browser can
            # exercise cancellation and interrupted-run recovery deterministically.
            await dispatch_gate.wait()
            if can_send() is not True:
                return {'status': 'unconfirmed'}
            return {'status': 'sent_unconfirmed'}

        app.state.fan_runtime.scene_command = synthetic_scene_command

        def qa_loopback(request):
            if not request.client or request.client.host not in ('127.0.0.1', '::1'):
                raise HTTPException(403)

        @app.get('/_qa/status')
        async def status(request: Request):
            qa_loopback(request)
            return {'fixture': 'synthetic-scenes', 'dispatches': len(commands),
                    'dispatch_held': not dispatch_gate.is_set()}

        @app.post('/_qa/control')
        async def control(request: Request):
            qa_loopback(request)
            value = await request.json()
            if value == {'mode': 'hold'}:
                dispatch_gate.clear()
            elif value == {'mode': 'release'}:
                dispatch_gate.set()
            else:
                raise HTTPException(422, 'Choose hold or release.')
            return {'dispatch_held': not dispatch_gate.is_set()}

        @app.get('/_qa/reopen')
        async def reopen(request: Request):
            qa_loopback(request)
            # Construct new stores against the same temporary SQLite database
            # to verify the saved scene, journal and permission fingerprint.
            saved = Scenes(service.scenes.storage)
            policy = RemoteScenePolicy(service.scenes.storage)
            return {'night': saved.definitions['night'], 'runs': saved.runs,
                    'remote': policy.configuration(saved.definitions)['scenes']}

        # The production static-site catch-all is registered in create_app;
        # keep fixture-only diagnostics ahead of it so they remain JSON routes.
        qa_routes = [route for route in app.router.routes
                     if getattr(route, 'path', '').startswith('/_qa/')]
        app.router.routes[:] = [route for route in app.router.routes if route not in qa_routes]
        fallback = next((index for index, route in enumerate(app.router.routes)
                         if getattr(route, 'path', '') == '/{path:path}'), len(app.router.routes))
        app.router.routes[fallback:fallback] = qa_routes

        async def tick():
            while True:
                service.tick()
                await asyncio.sleep(1)

        @asynccontextmanager
        async def lifespan(_):
            jobs = [asyncio.create_task(tick()), asyncio.create_task(app.state.scene_runtime.run())]
            try:
                yield
            finally:
                for job in jobs:
                    job.cancel()
                for job in jobs:
                    with suppress(asyncio.CancelledError):
                        await job
                await app.state.scene_runtime.close()
                app.state.room_runtime.close()
                app.state.transit_runtime.close()
                app.state.weather.client.client.close()

        app.router.lifespan_context = lifespan
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8751, log_level='warning'))

        async def deadline():
            await asyncio.sleep(1200)
            server.should_exit = True

        timeout = asyncio.create_task(deadline())
        print('Synthetic scene QA: http://127.0.0.1:8751/?setup=extras. Temporary data, synthetic devices only; 20-minute limit.', flush=True)
        try:
            await server.serve()
        finally:
            timeout.cancel()


def observed_time(offset):
    from datetime import UTC, datetime
    return datetime(2026, 9, 28, 21, offset, tzinfo=UTC)


if __name__ == '__main__':
    asyncio.run(main())
