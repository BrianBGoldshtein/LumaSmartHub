"""Temporary, loopback-only UI QA with real HTTP/WS/storage, synthetic Google.

No provider/hardware workers. Run directly; expires after 15min. No owner data.
"""
import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn

from luma.api import create_app
from luma.models import CalendarEvent


async def main():
    with TemporaryDirectory(prefix='luma-dates-qa-') as directory:
        app=create_app(data_dir=directory,frontend_dir=Path(__file__).resolve().parents[2]/'frontend'/'dist')
        service=app.state.luma
        # First-run setup needs no phone. Disable microphone; no real workers.
        service.update_settings({'voice_enabled':False,'theme':'hearth'})
        google=app.state.google
        google.authorized=lambda:True
        google.configured=lambda:True
        google.list_calendars=lambda:[{'id':'qa','summary':'Synthetic QA','background_color':'#7986cb'}]
        google.event_colors=lambda:[]
        def sample(event_id='qaevent'):
            now=datetime.now(UTC)+timedelta(days=7)
            return CalendarEvent(event_id,'qa','QA linked event',now,now+timedelta(hours=1),calendar_color='#7986cb')
        google.countdown_candidates=lambda **kw:{'events':[sample('qaevent2' if kw.get('page_token') else 'qaevent')], 'next_page':None if kw.get('page_token') else 'second'}
        google.countdown_event=lambda **kw:{'event':sample(kw['event_id']),'state':'ready'}
        # Any unexpected attempt to use a real provider fails closed.
        def forbidden(*args,**kwargs):raise AssertionError('No external provider permitted in UI fixture')
        google._service=forbidden
        async def tick():
            while True:
                service.tick()
                await asyncio.sleep(1)
        @asynccontextmanager
        async def lifespan(_):
            task=asyncio.create_task(tick())
            try:yield
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):await task
                app.state.weather.client.client.close()
        app.router.lifespan_context=lifespan
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8747,log_level='warning'))
        async def deadline():
            await asyncio.sleep(900)
            server.should_exit=True
        deadline_task=asyncio.create_task(deadline())
        print('Synthetic dates QA: http://127.0.0.1:8747/?setup=extras. Temporary data; no providers/hardware; 15min limit.',flush=True)
        try:await server.serve()
        finally:deadline_task.cancel()


if __name__=='__main__':asyncio.run(main())
