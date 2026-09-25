"""
Run coroutines from synchronous code on one long-lived event loop.

Loop-bound clients such as the aiocache Redis connection pool must always be
used from the event loop they were created on. The API used to create a fresh
event loop per Flask request, so pooled Redis connections outlived their loop
and failed with "attached to a different loop" / "Event loop is closed" while
the process's memory kept growing. Sync routes submit their coroutines here
instead, so every async call in the process shares a single loop.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from collections.abc import Coroutine
from typing import Any, Optional, TypeVar

T = TypeVar("T")

_loop: Optional[asyncio.AbstractEventLoop] = None
_loop_thread: Optional[threading.Thread] = None
_lock = threading.Lock()


def _get_loop() -> asyncio.AbstractEventLoop:
    """Return the shared loop, starting its daemon thread on first use."""
    global _loop, _loop_thread
    with _lock:
        if _loop is None:
            _loop = asyncio.new_event_loop()
            _loop_thread = threading.Thread(
                target=_loop.run_forever, name="async-bridge", daemon=True
            )
            _loop_thread.start()
        return _loop


def run_sync(coro: Coroutine[Any, Any, T], timeout: Optional[float] = None) -> T:
    """Run ``coro`` on the shared loop and block the calling thread for its result.

    Must not be called from the shared loop's own thread (it would deadlock).
    """
    loop = _get_loop()
    if threading.current_thread() is _loop_thread:
        coro.close()
        raise RuntimeError("run_sync() called from the async bridge loop thread")
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(timeout)
    except concurrent.futures.TimeoutError:
        future.cancel()
        raise
