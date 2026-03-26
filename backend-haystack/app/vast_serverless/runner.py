"""
Dedicated asyncio loop in a background thread so vastai SDK (aiohttp) works from sync Haystack .run().

Callers use submit(coro) which schedules work on that loop and blocks for the result.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Coroutine, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None
_started = threading.Event()
_lock = threading.Lock()


def _loop_main() -> None:
    global _loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _loop = loop
    _started.set()
    loop.run_forever()


def get_loop() -> asyncio.AbstractEventLoop:
    """Return the dedicated event loop (starts background thread on first use)."""
    global _thread
    with _lock:
        if _thread is None or not _thread.is_alive():
            _started.clear()
            _thread = threading.Thread(target=_loop_main, name="vast-serverless-loop", daemon=True)
            _thread.start()
            if not _started.wait(timeout=30):
                raise RuntimeError("Vast Serverless background loop failed to start")
    assert _loop is not None
    return _loop


def submit(coro: Coroutine[Any, Any, T], timeout: float | None = 600.0) -> T:
    """Run *coro* on the dedicated loop from any thread (including FastAPI worker threads)."""
    loop = get_loop()
    fut = asyncio.run_coroutine_threadsafe(coro, loop)
    return fut.result(timeout=timeout)
