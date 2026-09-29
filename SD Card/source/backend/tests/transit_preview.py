"""Loopback-only, temporary transit UI QA. No external providers or hardware.

Uses the real API, SQLite, WebSocket and frontend. Only the provider transport is
synthetic. Fixture control routes exist ONLY in this test executable; never ship
them in the service. Automatic shutdown after20min; all fixture state is deleted.
"""
import asyncio
from contextlib import asynccontextmanager,suppress
from datetime import UTC,datetime,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
import uvicorn
from fastapi import HTTPException,Request

from luma.api import create_app
from luma.transit_transport import TransitBudget,TransitTransport

TOKEN='synthetic_transit_fixture_token_only'


async def main():
    with TemporaryDirectory(prefix='luma-transit-qa-') as directory:
        app=create_app(data_dir=directory,frontend_dir=Path(__file__).resolve().parents[2]/'frontend'/'dist')
        service=app.state.luma;runtime=app.state.transit_runtime
        service.update_settings({'voice_enabled':False,'theme':'hearth'})
        service.display_clock_trusted=lambda:True
        service.transit.set_token(TOKEN)
        mode={'value':'normal'}

        def provider(request):
            if mode['value']=='offline':raise httpx.ConnectError('Synthetic offline',request=request)
            if mode['value']=='quota':return httpx.Response(429,json={'error':'synthetic'})
            if mode['value']=='malformed':return httpx.Response(200,json={'not':'a feed'})
            endpoint=request.url.path.split('/')[-1]
            if endpoint=='operators':payload={'content':[{'Id':'QA','Name':'QA Transit','SiriOperatorRef':'QA-RT','Monitored':True}]}
            elif endpoint=='lines':payload={'content':[{'Id':'QA:local','Name':'QA Local','SiriLineRef':'LOCAL','OperatorRef':'QA','Monitored':True}]}
            elif endpoint=='stops':payload={'Contents':{'dataObjects':{'ScheduledStopPoint':[
                {'id':f'STOP{i:02}','Name':f'QA stop {i:02}','Extensions':{'LocationType':'0','PlatformCode':str(i+1)}} for i in range(45)]}}}
            elif endpoint in ('StopMonitoring','stoptimetable'):
                now=datetime.now(UTC);live=endpoint=='StopMonitoring';stop=request.url.params.get('stopcode') or request.url.params.get('monitoringref')
                visits=[]
                for i in range(6):
                    call={'StopPointRef':stop,'AimedDepartureTime':(now+timedelta(minutes=10+i*5)).isoformat(),
                          'ExpectedDepartureTime':(now+timedelta(minutes=8+i*5)).isoformat()}
                    journey={'LineRef':'LOCAL','DirectionRef':'N' if i%2==0 else 'S','Monitored':True,
                             'PublishedLineName':'Local','DestinationName':'QA destination',
                             ('MonitoredCall' if live else 'TargetedCall'):call}
                    visits.append({'RecordedAtTime':now.isoformat(),('MonitoredVehicleJourney' if live else 'TargetedVehicleJourney'):journey})
                payload={'Siri':{'ServiceDelivery':{('StopMonitoringDelivery' if live else 'StopTimetableDelivery'):{
                    'ResponseTimestamp':now.isoformat(),('MonitoredStopVisit' if live else 'TimetabledStopVisit'):visits}}}}
            else:raise AssertionError('Unexpected provider endpoint in fixture')
            return httpx.Response(200,json=payload)

        runtime.close()
        runtime.transport=TransitTransport(TransitBudget(service.storage),service.transit.token,transport=httpx.MockTransport(provider))
        runtime.directory.transport=runtime.transport

        @app.post('/_qa/control')
        async def control(request:Request):
            if request.client.host not in ('127.0.0.1','::1') or request.headers.get('origin') not in (None,'http://127.0.0.1:8749'):
                raise HTTPException(403)
            body=await request.json()
            if body.get('mode','normal') not in ('normal','offline','quota','malformed'):raise HTTPException(422)
            mode['value']=body.get('mode','normal')
            if body.get('reset_refresh'):runtime.next_request=0;runtime.backoff.clear()
            if body.get('clear_directory'):
                with service.storage.transaction() as connection:connection.execute("DELETE FROM cache WHERE namespace='transit_directory'")
            return {'mode':mode['value']}

        async def tick():
            while True:service.tick();await asyncio.sleep(1)
        @asynccontextmanager
        async def lifespan(_):
            task=asyncio.create_task(tick())
            try:yield
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):await task
                runtime.close();app.state.weather.client.client.close()
        app.router.lifespan_context=lifespan
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8749,log_level='warning'))
        async def deadline():await asyncio.sleep(1200);server.should_exit=True
        deadline_task=asyncio.create_task(deadline())
        print('Synthetic transit QA: http://127.0.0.1:8749/?setup=extras. Temporary data, no providers/hardware,20min limit.',flush=True)
        try:await server.serve()
        finally:deadline_task.cancel()


if __name__=='__main__':asyncio.run(main())
