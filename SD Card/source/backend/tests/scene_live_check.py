"""Real HTTP/WebSocket release check for scene_preview.py's synthetic fixture.

Refuses non-loopback hosts and verifies persistence, revision guards, manual
run receipts, narrow remote consent, stale review, and WebSocket delivery.
"""
import asyncio
import json

import httpx
import websockets


BASE = 'http://127.0.0.1:8751'


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=5) as client:
        check = await client.get('/_qa/status')
        assert check.status_code == 200 and check.json()['fixture'] == 'synthetic-scenes'

        initial = (await client.get('/api/v1/scenes')).json()
        assert all(not row['enabled'] and not row['automatic'] and not row['actions']
                   for row in initial['definitions'].values())
        fan = next(row for row in initial['devices'] if row['id'] == 'fan_1')
        off = next(row for row in fan['actions'] if row['action'] == 'power_off')
        on = next(row for row in fan['actions'] if row['action'] == 'power_on')

        # Listen on the production WebSocket, then persist and manually run a
        # scene through the production HTTP API.
        async with websockets.connect('ws://127.0.0.1:8751/api/v1/events',
                                      origin=BASE) as socket:
            first = json.loads(await asyncio.wait_for(socket.recv(), 5))
            assert first['type'] == 'snapshot'
            assert 'privacy_redacted' in first['data']

            edit = {'revision': initial['revision'], 'enabled': True, 'automatic': False,
                    'actions': [{key: off[key] for key in ('device', 'action', 'value', 'binding')}]}
            saved = await client.put('/api/v1/scenes/night', json=edit)
            assert saved.status_code == 200, saved.text
            saved_config = saved.json()
            assert saved_config['definitions']['night']['enabled']
            assert saved_config['definitions']['night']['actions'][0]['action'] == 'power_off'
            assert saved_config['definitions']['night']['automatic'] is False

            stale = await client.put('/api/v1/scenes/night', json=edit)
            assert stale.status_code == 409, stale.text

            run = await client.post('/api/v1/scenes/night/run', json={'revision': saved_config['revision']})
            assert run.status_code == 200, run.text
            result = run.json()['result']
            assert result['scene'] == 'night' and result['source'] == 'manual'
            assert [step['status'] for step in result['steps']] == ['unconfirmed'], result

            # Remote consent is a separate explicit action. Changing the saved
            # action afterward makes that exact-content grant stale.
            remote = saved_config['remote']
            grant = await client.put('/api/v1/scenes/remote', json={
                'revision': remote['revision'], 'enabled': True, 'scenes': ['night']})
            assert grant.status_code == 200, grant.text
            assert grant.json()['remote']['scenes']['night']['allowed'] is True

            fresh = grant.json()
            revised = await client.put('/api/v1/scenes/night', json={
                'revision': fresh['revision'], 'enabled': True, 'automatic': False,
                'actions': [{key: on[key] for key in ('device', 'action', 'value', 'binding')}]})
            assert revised.status_code == 200, revised.text
            permission = revised.json()['remote']['scenes']['night']
            assert permission['allowed'] is False and permission['needs_review'] is True

            token = (await client.get('/api/v1/security/lan-token')).json()['token']
            remote_run = await client.post('/api/v1/shortcut-command',
                                           headers={'X-Luma-Token': token},
                                           json={'name': 'run_remote_scene', 'value': 'night'})
            assert remote_run.status_code == 200, remote_run.text
            assert remote_run.json()['accepted'] is False
            assert 'not allowlisted' in remote_run.json()['message']

            # Check the durable records through fresh storage objects rather
            # than only the runtime's already-loaded in-memory state.
            reopened = (await client.get('/_qa/reopen')).json()
            assert reopened['night']['enabled'] and reopened['night']['actions'][0]['action'] == 'power_on'
            assert len(reopened['runs']) == 1 and reopened['runs'][0]['steps'][0]['status'] == 'unconfirmed'
            assert reopened['remote']['night']['needs_review'] is True

            # Consume published scene events and assert no raw IR bytes or
            # synthetic provider credentials are disclosed over the socket.
            messages = []
            while len(messages) < 12:
                item = json.loads(await asyncio.wait_for(socket.recv(), 3))
                messages.append(item)
                if item.get('type') == 'scenes.updated':
                    assert 'data' in item
                    break
            assert any(item.get('type') == 'scenes.updated' for item in messages)
            wire = json.dumps(messages)
            assert 'carrier_hz' not in wire and 'durations' not in wire and 'synthetic_' not in wire

        dispatched = (await client.get('/_qa/status')).json()['dispatches']
        assert dispatched == 1, f'Expected one synthetic dispatch, saw {dispatched}'
        print('PASS: real HTTP save/reload/run, stale revision rejection, exact remote grant invalidation, token-authenticated remote rejection, durable journal reload, and WebSocket update; synthetic fixture only.', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
