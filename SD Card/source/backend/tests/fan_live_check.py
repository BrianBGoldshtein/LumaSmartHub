"""Real local HTTP/WebSocket checks for fan_preview.py's synthetic IR fixture."""
import asyncio
import json

import httpx
import websockets


BASE = 'http://127.0.0.1:8752'
DEVICE_ID = 'usb-ir-' + 'a' * 24


async def pause_for_runtime():
    # FanRuntime has an intentional one-second inter-operation pacing gate.
    await asyncio.sleep(1.05)


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=8) as client:
        status = await client.get('/_qa/status')
        assert status.status_code == 200 and status.json()['fixture'] == 'synthetic-fans'
        assert (await client.post('/_qa/control', json={'mode': 'normal'})).status_code == 200

        config = (await client.get('/api/v1/fans')).json()
        assert all(row['route'] is None and row['buttons'] == [] for row in config['fans'])
        async with websockets.connect('ws://127.0.0.1:8752/api/v1/events', origin=BASE) as socket:
            initial = json.loads(await asyncio.wait_for(socket.recv(), 5))
            assert initial['type'] == 'snapshot'
            # A fresh uncommissioned hub starts in the private/redacted state;
            # setup APIs remain local-owner gated by their existing policy.
            assert initial['data']['privacy_redacted'] is True

            discovery = await client.post('/api/v1/fans/discover', json={'revision': config['revision']})
            assert discovery.status_code == 200, discovery.text
            found = discovery.json()['devices']
            assert len(found) == 1 and found[0]['id'] == DEVICE_ID
            assert found[0]['serial_present'] and found[0]['send'] and found[0]['receive']

            for fan, emitter, label in (('fan_1', 1, 'Desk fan'), ('fan_2', 2, 'Bedside fan')):
                await pause_for_runtime()
                selected = await client.post('/api/v1/fans/select', json={
                    'revision': config['revision'], 'fan': fan, 'device_id': DEVICE_ID,
                    'emitter': emitter, 'name': label})
                assert selected.status_code == 200, selected.text
                config = selected.json()

            # Learn/test/observe one absolute state and repeat the already-same
            # state observation, then prove fan 1 is only scene-eligible when
            # fan 2 also has an independent observed button.
            await pause_for_runtime()
            learned = await client.post('/api/v1/fans/learn', json={
                'revision': config['revision'], 'fan': 'fan_1', 'button': 'power_off',
                'receiver_id': DEVICE_ID, 'carrier_hz': None})
            assert learned.status_code == 200, learned.text
            config = learned.json()
            secret_free = json.dumps(config)
            assert 'carrier_hz' not in secret_free and 'durations' not in secret_free
            assert 'signal' not in secret_free and 'QA_SECRET_SENTINEL' not in secret_free

            await pause_for_runtime()
            first = await client.post('/api/v1/fans/test', json={
                'revision': config['revision'], 'fan': 'fan_1', 'button': 'power_off', 'confirmed': True})
            assert first.status_code == 200, first.text
            first_result = first.json()['result']
            assert first_result['status'] == 'sent_unconfirmed'
            config = first.json()['configuration']

            await pause_for_runtime()
            observed = await client.post('/api/v1/fans/observe', json={
                'revision': config['revision'], 'fan': 'fan_1', 'command_id': first_result['id'],
                'expected_state': True, 'other_unchanged': True})
            assert observed.status_code == 200, observed.text
            config = observed.json()

            await pause_for_runtime()
            second = await client.post('/api/v1/fans/test', json={
                'revision': config['revision'], 'fan': 'fan_1', 'button': 'power_off', 'confirmed': True})
            assert second.status_code == 200, second.text
            second_result = second.json()['result']
            config = second.json()['configuration']

            await pause_for_runtime()
            repeated = await client.post('/api/v1/fans/observe', json={
                'revision': config['revision'], 'fan': 'fan_1', 'command_id': second_result['id'],
                'expected_state': True, 'other_unchanged': True, 'repeat_same_state': True})
            assert repeated.status_code == 200, repeated.text
            config = repeated.json()
            fan1 = next(row for row in config['fans'] if row['id'] == 'fan_1')
            assert fan1['buttons'][0]['checks'] == 2 and not fan1['buttons'][0]['scene_eligible']

            # Give fan 2 one observed state: independence is now proven, and
            # the already-two-checked absolute fan 1 action becomes eligible.
            await pause_for_runtime()
            learned2 = await client.post('/api/v1/fans/learn', json={
                'revision': config['revision'], 'fan': 'fan_2', 'button': 'power_off',
                'receiver_id': DEVICE_ID, 'carrier_hz': None})
            assert learned2.status_code == 200, learned2.text
            config = learned2.json()
            await pause_for_runtime()
            fan2test = await client.post('/api/v1/fans/test', json={
                'revision': config['revision'], 'fan': 'fan_2', 'button': 'power_off', 'confirmed': True})
            assert fan2test.status_code == 200, fan2test.text
            fan2result = fan2test.json()['result']
            config = fan2test.json()['configuration']
            await pause_for_runtime()
            fan2observe = await client.post('/api/v1/fans/observe', json={
                'revision': config['revision'], 'fan': 'fan_2', 'command_id': fan2result['id'],
                'expected_state': True, 'other_unchanged': True})
            assert fan2observe.status_code == 200, fan2observe.text
            config = fan2observe.json()
            fan1 = next(row for row in config['fans'] if row['id'] == 'fan_1')
            assert config['independent'] is True and fan1['buttons'][0]['scene_eligible'] is True
            assert config['remote_control'] is False

            # A USB boundary failure after the receipt claim is returned as a
            # fixed error; the durable outcome stays unknown and cannot replay.
            await pause_for_runtime()
            await client.post('/_qa/control', json={'mode': 'unavailable'})
            failing = await client.post('/api/v1/fans/command', json={
                'revision': config['revision'], 'fan': 'fan_1', 'button': 'power_off', 'confirmed': True})
            assert failing.status_code == 503 and 'QA_USB' not in failing.text and 'QA_SECRET' not in failing.text
            uncertain = (await client.get('/api/v1/fans')).json()
            receipt = next(row for row in uncertain['fans'] if row['id'] == 'fan_1')['last_command']
            assert receipt['status'] == 'unknown'

            # A blocked learn makes a competing discover return 429 rather
            # than queueing; explicit cancellation records no late button.
            await pause_for_runtime()
            await client.post('/_qa/control', json={'mode': 'block_learn'})
            latest = (await client.get('/api/v1/fans')).json()
            pending = asyncio.create_task(client.post('/api/v1/fans/learn', json={
                'revision': latest['revision'], 'fan': 'fan_1', 'button': 'power_on',
                'receiver_id': DEVICE_ID, 'carrier_hz': None}))
            for _ in range(40):
                qa = (await client.get('/_qa/status')).json()
                if qa['learn_started']:
                    break
                await asyncio.sleep(.05)
            else:
                raise AssertionError('Synthetic learn never reached its blocked transport.')
            calls_before_busy = len(qa['actions'])
            busy = await client.post('/api/v1/fans/discover', json={'revision': latest['revision']})
            assert busy.status_code == 429, busy.text
            await client.post('/api/v1/fans/cancel', json={})
            cancelled = await pending
            assert cancelled.status_code == 409, cancelled.text
            final = (await client.get('/api/v1/fans')).json()
            assert 'power_on' not in [row['key'] for row in next(row for row in final['fans'] if row['id'] == 'fan_1')['buttons']]
            qa = (await client.get('/_qa/status')).json()
            assert qa['cancellations'] == 1 and len(qa['actions']) == calls_before_busy

            # Scene changes were delivered through the actual WebSocket and its
            # snapshot contains no waveform or fake transport exception text.
            observed_messages = []
            while len(observed_messages) < 20:
                item = json.loads(await asyncio.wait_for(socket.recv(), 3))
                observed_messages.append(item)
                if item.get('type') == 'fans.updated':
                    break
            assert any(item.get('type') == 'fans.updated' for item in observed_messages)
            wire = json.dumps(observed_messages)
            assert 'carrier_hz' not in wire and 'durations' not in wire
            assert 'QA_SECRET_SENTINEL' not in wire and 'QA_USB' not in wire

        print('PASS: real HTTP/WS fan discovery→selection→learn→repeatable tests/observations; action eligibility; sanitized uncertain receipt; bounded busy/no-queue and cancellation; no IR secrets in API/socket. Fake transport only.', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
