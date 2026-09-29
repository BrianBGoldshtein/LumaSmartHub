"""Bounded, isolated real-HTTP/WS night QA fixture; never operates hardware.

Run from source/backend: .venv/Scripts/python.exe tests/night_preview.py
Open http://127.0.0.1:8746. All state is temporary; no provider workers run.
The simulated panel exercises the actual bridge worker and frame handoff API.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

import httpx
import uvicorn

from luma.api import create_app
from luma.device_agent import DisplayJobWorker
from luma.models import CalendarEvent


class SimulatedPanel:
    def set_brightness_confirmed(self, value):
        return True

    def power(self, value):
        return True


async def main():
    with TemporaryDirectory(prefix='luma-night-qa-') as directory:
        app = create_app(data_dir=directory, frontend_dir=Path(__file__).resolve().parents[2]/'frontend'/'dist')
        service = app.state.luma
        service.display_clock_trusted = lambda: True
        service.update_settings({'onboarding_completed': True, 'voice_enabled': False,
                                 'visible_calendar_ids': ['sample'], 'sleep_calendar_ids': ['sleep']})
        now = datetime.now(UTC)
        service.replace_events([
            CalendarEvent('private-sample','sample','PRIVATE QA APPOINTMENT',now,now+timedelta(hours=1)),
            CalendarEvent('sleep-sample','sleep','Sleep',now-timedelta(hours=1),now+timedelta(hours=1)),
        ])
        service.unlock_with_pin()
        stop = Event()

        def bridge():
            with ThreadPoolExecutor(max_workers=1) as executor, httpx.Client(base_url='http://127.0.0.1:8746',timeout=2) as client:
                worker=DisplayJobWorker(SimulatedPanel(),executor)
                while not stop.wait(.2):
                    try:
                        worker.poll(client,client.get('/api/v1/state').json())
                    except httpx.HTTPError:
                        pass

        async def tick():
            while True:
                service.timer_tick(trusted=True)
                await asyncio.sleep(1)

        @asynccontextmanager
        async def lifespan(_):
            tasks=[asyncio.create_task(tick()),asyncio.create_task(asyncio.to_thread(bridge))]
            try:
                yield
            finally:
                stop.set()
                tasks[0].cancel()
                with suppress(asyncio.CancelledError): await tasks[0]
                await tasks[1]
                app.state.weather.client.client.close()

        app.router.lifespan_context=lifespan
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8746,log_level='warning'))
        async def deadline():
            await asyncio.sleep(600)
            server.should_exit=True
        deadline_task=asyncio.create_task(deadline())
        print('Isolated night fixture on 127.0.0.1:8746; stops after 10 minutes. No hardware or providers.',flush=True)
        try: await server.serve()
        finally: deadline_task.cancel()


if __name__=='__main__':
    asyncio.run(main())
