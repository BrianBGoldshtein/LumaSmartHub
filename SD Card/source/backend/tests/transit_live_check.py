"""Run ONLY against transit_preview.py's disposable loopback fixture on8749.

Requires the browser-created/edited private favorite. Exercises real HTTP and
WebSocket transport, not TestClient. Never accepts an arbitrary host or token.
"""
import asyncio
import json

import httpx
import websockets


async def main():
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8749',timeout=5) as client:
        control=await client.post('/_qa/control',json={'mode':'normal','reset_refresh':True})
        assert control.status_code==200 and control.json()=={'mode':'normal'}, 'Not the disposable QA fixture'
        config=(await client.get('/api/v1/transit')).json()
        assert len(config['items'])==1
        private=config['items'][0]
        assert private['title']=='QA private commute edited' and not private['public']
        assert private['stop_id']=='STOP40' and private['direction']=='N' and private['line']=='LOCAL'
        assert config['token_configured'] and 'synthetic_transit_fixture_token_only' not in json.dumps(config)
        response=await client.post('/api/v1/transit/favorites',json={
            'title':'QA public stop','operator_id':'QA','stop_id':'STOP40',
            'route_id':'QA:local','direction':'S','public':True})
        assert response.status_code==200,response.text
        public=next(item for item in response.json()['items'] if item['public'])
        # Fixture-only PIN; no owner credentials or production settings.
        assert (await client.post('/api/v1/security/pin',json={'pin':'246810'})).status_code==200
        assert (await client.post('/api/v1/security/unlock',json={'pin':'246810'})).status_code==200
        assert (await client.patch('/api/v1/settings',json={'onboarding_completed':True})).status_code==200
        refreshed=await client.post('/api/v1/transit/refresh',json={'item_id':private['id']})
        assert refreshed.status_code==200,refreshed.text
        views=refreshed.json()['views']
        assert len(views)==2 and all(len(view['departures'])==3 for view in views)
        assert all(row['kind']=='predicted' and row['prediction_until'] and row['scheduled_at'] for view in views for row in view['departures'])
        summary=(await client.get('/api/v1/onboarding')).json()['summary']
        assert (summary['transit_stops'],summary['public_transit_stops'],summary['transit_token'])==(2,1,True)
        assert 'QA public stop' not in json.dumps(summary) and 'synthetic_transit_fixture_token_only' not in json.dumps(summary)
        async with websockets.connect('ws://127.0.0.1:8749/api/v1/events',origin='http://127.0.0.1:8749') as socket:
            full=json.loads(await asyncio.wait_for(socket.recv(),5))['data']
            assert not full['privacy_redacted'] and len(full['transit'])==2
            assert (await client.post('/api/v1/commands',json={'name':'privacy_now','source':'touchscreen'})).status_code==200
            for _ in range(10):
                private_view=json.loads(await asyncio.wait_for(socket.recv(),5))['data']
                if private_view['privacy_redacted']:break
            assert private_view['privacy_redacted']
            assert [row['id'] for row in private_view['transit']]==[public['id']]
            assert 'QA private commute edited' not in json.dumps(private_view)
            assert (await client.get('/api/v1/transit')).status_code==403
            assert (await client.post('/api/v1/transit/visible',json={'item_id':private['id']})).status_code==403
            assert (await client.post('/api/v1/transit/visible',json={'item_id':public['id']})).status_code==200
        assert (await client.post('/api/v1/security/unlock',json={'pin':'246810'})).status_code==200
        print('PASS: browser favorite persisted/edited; shared stop predictions; nonsecret setup summary; real WS privacy redaction; setup403 and visible-stop gate.',flush=True)


if __name__=='__main__':asyncio.run(main())
