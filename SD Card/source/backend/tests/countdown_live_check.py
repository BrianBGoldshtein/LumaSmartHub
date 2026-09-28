"""Run ONLY against the temporary countdown_preview.py fixture on port8747."""
import asyncio
import json

import httpx
import websockets


async def main():
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8747',timeout=5) as client:
        response=await client.get('/api/v1/countdowns')
        if response.status_code==403:
            assert (await client.post('/api/v1/security/unlock',json={'pin':'246810'})).status_code==200
            response=await client.get('/api/v1/countdowns')
        config=response.json()
        assert {item['title'] for item in config['items']}=={'QA birthday','QA linked event'}, 'Requires synthetic browser-created fixtures'
        manual=next(item for item in config['items'] if item['title']=='QA birthday')
        assert manual['date']=='2026-12-10' and not manual['public']
        # Test-only PIN, not owner credentials; fixture storage is temporary.
        assert (await client.post('/api/v1/security/pin',json={'pin':'246810'})).status_code==200
        assert (await client.post('/api/v1/security/unlock',json={'pin':'246810'})).status_code==200
        assert (await client.patch('/api/v1/settings',json={'onboarding_completed':True})).status_code==200
        async with websockets.connect('ws://127.0.0.1:8747/api/v1/events',origin='http://127.0.0.1:8747') as socket:
            full=json.loads(await asyncio.wait_for(socket.recv(),5))['data']
            assert len(full['countdowns'])==2 and not full['privacy_redacted']
            response=await client.post('/api/v1/commands',json={'name':'privacy_now','source':'touchscreen'})
            assert response.status_code==200
            for _ in range(10):
                private=json.loads(await asyncio.wait_for(socket.recv(),5))['data']
                if private['privacy_redacted']:break
            assert private['privacy_redacted']
            assert [item['title'] for item in private['countdowns']]==['QA linked event']
            assert (await client.get('/api/v1/countdowns')).status_code==403
        print('PASS: browser-created dates persisted; real WebSocket full-to-private redaction; public pin retained; setup403 while locked.',flush=True)


if __name__=='__main__':asyncio.run(main())
