"""Dedicated asyncio loop for Playwright (Windows-safe with uvicorn --reload).

Uvicorn on Windows + --reload uses SelectorEventLoop, which cannot spawn
Playwright's driver subprocess. All Playwright coroutines run on a background
thread with ProactorEventLoop instead.
"""
from __future__ import annotations

import asyncio
import sys
import threading
from collections.abc import Awaitable
from typing import TypeVar

T = TypeVar("T")

_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None
_ready = threading.Event()
_lock = threading.Lock()


def _thread_main() -> None:
    global _loop
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _loop = loop
    _ready.set()
    loop.run_forever()


def _ensure_started() -> asyncio.AbstractEventLoop:
    global _thread
    with _lock:
        if _thread is None:
            _thread = threading.Thread(target=_thread_main, name="playwright-asyncio", daemon=True)
            _thread.start()
    _ready.wait()
    assert _loop is not None
    return _loop


async def run(coro: Awaitable[T]) -> T:
    """Run a Playwright coroutine on the browser thread's event loop."""
    if not asyncio.iscoroutine(coro):
        raise TypeError("pw_loop.run() expects a coroutine object")
    pw_loop = _ensure_started()
    caller = asyncio.get_running_loop()
    if pw_loop is caller:
        return await coro
    fut = asyncio.run_coroutine_threadsafe(coro, pw_loop)
    return await asyncio.wrap_future(fut)


async def shutdown() -> None:
    """Stop the background loop (after Playwright is torn down)."""
    global _loop, _thread
    if _loop is None or _thread is None:
        return
    loop = _loop
    thread = _thread

    async def _stop() -> None:
        loop.stop()

    await run(_stop())
    thread.join(timeout=5)
    _loop = None
    _thread = None
    _ready.clear()
