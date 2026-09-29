"""Only for room_preview.py's disposable fixture on port8750; no real account."""
import asyncio
import json

import httpx
import websockets


async def main():
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8750', timeout=5, trust_env=False) as client:
        response = await client.post('/_qa/control', json={'mode': 'normal', 'locked': False})
        assert response.status_code == 200 and set(response.json()) == {'commands', 'connected', 'selected'}
        count = response.json()['commands']
        config = (await client.get('/api/v1/room')).json()
        assert config['connected'] and config['selected']['name'] == 'Bedroom purifier'
        assert not config['remote_control'] and not config['recovery_error']
        assert all(value not in json.dumps(config) for value in ('QA_TOKEN_SENTINEL', 'QA_ACCOUNT_SENTINEL', 'QA_CID_SENTINEL', 'synthetic-password-only'))
        summary = (await client.get('/api/v1/onboarding')).json()['summary']
        assert summary['purifier_session'] and summary['purifier_selected'] and not summary['room_recovery']
        assert 'Bedroom purifier' not in json.dumps(summary)
        async with websockets.connect('ws://127.0.0.1:8750/api/v1/events', origin='http://127.0.0.1:8750', proxy=None) as socket:
            full = json.loads(await asyncio.wait_for(socket.recv(), 5))['data']
            assert not full['privacy_redacted'] and full['room']['device']['name'] == 'Bedroom purifier'
            assert (await client.post('/_qa/control', json={'locked': True})).status_code == 200
            for _ in range(10):
                locked = json.loads(await asyncio.wait_for(socket.recv(), 5))['data']
                if locked['privacy_redacted']: break
            assert locked['privacy_redacted'] and locked['room'] is None
            assert 'Bedroom purifier' not in json.dumps(locked)
            assert (await client.get('/api/v1/room')).status_code == 403
            assert (await client.post('/api/v1/room/purifier/command', json={'revision': config['revision'], 'action': 'power', 'value': True})).status_code == 403
        control = await client.post('/_qa/control', json={'locked': False})
        assert control.json()['commands'] == count, 'Privacy test must not send a command'
        assert (await client.get('/api/v1/room')).json()['selected'] == config['selected']
        print('PASS: browser-saved selection; secret-free config/review; real WS privacy redaction; locked API/command403; no unintended command.', flush=True)


if __name__ == '__main__': asyncio.run(main())
