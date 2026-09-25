"""Tests for the shared event loop used by the API's sync routes."""

import asyncio
import os
import sys
import threading

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from infra.async_bridge import run_sync


async def _running_loop() -> asyncio.AbstractEventLoop:
    return asyncio.get_running_loop()


def test_returns_result_and_propagates_errors():
    async def boom() -> None:
        raise ValueError("nope")

    async def add(a: int, b: int) -> int:
        await asyncio.sleep(0)
        return a + b

    assert run_sync(add(2, 3)) == 5
    with pytest.raises(ValueError, match="nope"):
        run_sync(boom())


def test_calls_from_many_threads_share_one_loop():
    loops: list[asyncio.AbstractEventLoop] = []

    def worker() -> None:
        loops.append(run_sync(_running_loop()))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(loops) == 8
    assert len({id(loop) for loop in loops}) == 1
    assert not loops[0].is_closed()


def test_loop_bound_objects_survive_between_calls():
    """A per-request loop broke this: prod logged "attached to a different loop"."""
    async def make_future() -> asyncio.Future:
        return asyncio.get_running_loop().create_future()

    async def resolve_and_await(fut: asyncio.Future) -> str:
        asyncio.get_running_loop().call_soon(fut.set_result, "done")
        return await fut

    fut = run_sync(make_future())
    assert run_sync(resolve_and_await(fut)) == "done"


def test_timeout_cancels_the_coroutine():
    cancelled = threading.Event()

    async def slow() -> None:
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    with pytest.raises(TimeoutError):
        run_sync(slow(), timeout=0.05)
    assert cancelled.wait(1)
