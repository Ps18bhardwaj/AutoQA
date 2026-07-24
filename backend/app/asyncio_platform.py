"""Windows asyncio compatibility for Playwright + uvicorn.

Uvicorn's default asyncio loop uses ``SelectorEventLoop`` when ``--reload`` is
enabled (``use_subprocess=True``). On Windows, SelectorEventLoop cannot run
``asyncio.create_subprocess_exec``, which Playwright needs to start its driver.
Force ``ProactorEventLoop`` instead.
"""
from __future__ import annotations

import asyncio
import sys

def patch_uvicorn_loop_for_playwright() -> None:
    """Make plain ``uvicorn ... --reload`` work on Windows (called at app import)."""
    if sys.platform != "win32":
        return
    import uvicorn.loops.asyncio as uv_asyncio

    def _loop_factory(use_subprocess: bool = False) -> type[asyncio.AbstractEventLoop]:
        return asyncio.ProactorEventLoop

    uv_asyncio.asyncio_loop_factory = _loop_factory


def loop_factory() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        return asyncio.ProactorEventLoop()
    return asyncio.SelectorEventLoop()
