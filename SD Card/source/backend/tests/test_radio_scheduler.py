import asyncio
from types import SimpleNamespace

import pytest

from luma.ancs_advertising import reconnect_adapter
from luma.radio_scheduler import RadioScheduler


@pytest.mark.asyncio
async def test_five_phone_jobs_are_fifo_and_never_simultaneous():
    scheduler = RadioScheduler()
    observed, active = [], 0
    async def job(uid):
        nonlocal active
        assert active == 0
        active += 1
        observed.append(uid)
        await asyncio.sleep(.01)
        active -= 1
    await asyncio.gather(*(scheduler.perform(str(uid), 'hci0', lambda uid=uid: job(uid)) for uid in range(5)))
    assert observed == list(range(5))
    assert scheduler._pending == set()


@pytest.mark.asyncio
async def test_shared_scan_budget_keeps_connect_attempts_for_all_phones():
    clock = [100.]
    scheduler = RadioScheduler(clock=lambda: clock[0])
    calls = []
    async def scan(uid): calls.append(('scan', uid)); return True
    async def connect(uid): calls.append(('connect', uid)); return True
    for uid in range(5):
        assert await scheduler.perform(str(uid), 'hci0', lambda uid=uid: scan(uid), scan=True, connect=lambda uid=uid: connect(uid))
    assert calls == [('scan', 0), ('connect', 1), ('connect', 2), ('connect', 3), ('connect', 4)]
    clock[0] += 30
    assert await scheduler.perform('0', 'hci0', lambda: scan(0), scan=True)
    assert calls[-1] == ('scan', 0)


@pytest.mark.asyncio
async def test_failed_or_cancelled_phone_releases_radio_and_does_not_cancel_other_jobs():
    scheduler = RadioScheduler()
    entered = asyncio.Event()
    release = asyncio.Event()
    async def slow(): entered.set(); await release.wait()
    async def fine(): return 'next phone worked'
    failed = asyncio.create_task(scheduler.perform('one', 'hci0', slow))
    await entered.wait()
    waiting = asyncio.create_task(scheduler.perform('two', 'hci0', fine))
    failed.cancel()
    with pytest.raises(asyncio.CancelledError): await failed
    assert await asyncio.wait_for(waiting, 1) == 'next phone worked'
    assert scheduler._pending == set()


@pytest.mark.asyncio
async def test_duplicate_job_cannot_monopolize_fifo():
    scheduler = RadioScheduler()
    entered = asyncio.Event()
    release = asyncio.Event()
    async def job(): entered.set(); await release.wait()
    task = asyncio.create_task(scheduler.perform('one', 'hci0', job))
    await entered.wait()
    with pytest.raises(RuntimeError): await scheduler.perform('one', 'hci0', job)
    release.set()
    await task


def test_backoff_is_bounded_per_user_and_only_stable_authorization_resets_it():
    clock = [100.]
    scheduler = RadioScheduler(clock=lambda: clock[0], jitter=lambda low, high: 1)
    assert [scheduler.failure_delay('one') for _ in range(8)] == [10, 20, 40, 80, 120, 120, 120, 120]
    assert scheduler.failure_delay('two') == 10
    scheduler.note_authorized('one')
    clock[0] += 30
    scheduler.note_authorized('one')
    assert scheduler.failure_delay('one') == 120
    scheduler.note_authorized('one')
    clock[0] += 61
    scheduler.note_authorized('one')
    assert scheduler.failure_delay('one') == 10
    scheduler.forget('two')
    assert scheduler.failure_delay('two') == 10


def test_shared_advertisement_does_not_stop_because_primary_is_connected():
    variant = lambda value: SimpleNamespace(value=value)
    objects = {
        '/adapter': {'org.bluez.Adapter1': {'Powered': variant(True)}, 'org.bluez.LEAdvertisingManager1': {}},
        '/primary': {'org.bluez.Device1': {key: variant(value) for key, value in {
            'Address': 'AA:BB:CC:DD:EE:01', 'Paired': True, 'Bonded': True, 'Trusted': True,
            'Connected': True, 'Adapter': '/adapter',
        }.items()}},
        '/secondary': {'org.bluez.Device1': {key: variant(value) for key, value in {
            'Address': 'AA:BB:CC:DD:EE:02', 'Paired': True, 'Bonded': True, 'Trusted': True,
            'Connected': False, 'Adapter': '/adapter',
        }.items()}},
    }
    assert reconnect_adapter(objects, ('AA:BB:CC:DD:EE:01', 'AA:BB:CC:DD:EE:02')) == '/adapter'
    objects['/secondary']['org.bluez.Device1']['Connected'] = variant(True)
    assert reconnect_adapter(objects, ('AA:BB:CC:DD:EE:01', 'AA:BB:CC:DD:EE:02')) is None
    objects['/secondary']['org.bluez.Device1']['Connected'] = variant(False)
    objects['/secondary']['org.bluez.Device1']['Trusted'] = variant(False)
    assert reconnect_adapter(objects, ('AA:BB:CC:DD:EE:01', 'AA:BB:CC:DD:EE:02')) is None
