"""Deterministic event/cancellation race; no BlueZ, radio or real account."""
import asyncio
from types import SimpleNamespace
import pytest
from luma.bluetooth_runtime import BluetoothRuntime


@pytest.mark.asyncio
async def test_connection_event_racing_shutdown_never_swallows_cancellation():
    runtime=SimpleNamespace(change_event=asyncio.Event())
    async def worker():
        await BluetoothRuntime.wait_change(runtime,120)
        await asyncio.Event().wait()  # Models the next worker iteration.
    task=asyncio.create_task(worker())
    try:
        await asyncio.sleep(0);await asyncio.sleep(0)
        runtime.change_event.set()
        asyncio.get_running_loop().call_soon(task.cancel)
        done,_=await asyncio.wait({task},timeout=.3)
        assert task in done and task.cancelled(), 'A connection event swallowed worker shutdown'
    finally:
        if not task.done():task.cancel()
        await asyncio.gather(task,return_exceptions=True)


@pytest.mark.asyncio
async def test_normal_event_and_timeout_both_clear_the_consumed_signal():
    runtime=SimpleNamespace(change_event=asyncio.Event())
    runtime.change_event.set()
    await BluetoothRuntime.wait_change(runtime,.01)
    assert not runtime.change_event.is_set()
    await BluetoothRuntime.wait_change(runtime,.01)
    assert not runtime.change_event.is_set()
