"""Playwright lifecycle + per-run browser sessions.

One Playwright + one Chromium for the process (launched from the FastAPI
lifespan, relaunched if it crashes); one BrowserContext + Page PER RUN for
cookie/storage isolation. LangGraph state carries only the run_id — Playwright
objects aren't checkpoint-serializable — so every graph node does
``get_session(run_id)``.

Console/network listeners attach once at session creation and accumulate into
run-scoped buffers; ``drain_*`` methods hand back only what's NEW since the
last observe step, so findings are never double-counted.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urldefrag

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from ..config import get_settings
from .. import safety
from ._pw_loop import run as pw_run
from ._pw_loop import shutdown as shutdown_pw_loop

logger = logging.getLogger("autoqa.browser")

_pw = None
_browser: Browser | None = None
_sessions: dict[str, "BrowserSession"] = {}


async def get_browser() -> Browser:
    """Process-wide Chromium, launched lazily, relaunched if it crashed."""

    async def _launch() -> Browser:
        global _pw, _browser
        if _browser is not None and _browser.is_connected():
            return _browser
        if _pw is None:
            _pw = await async_playwright().start()
        settings = get_settings()
        _browser = await _pw.chromium.launch(headless=settings.headless)
        logger.info("[browser] chromium launched (headless=%s)", settings.headless)
        return _browser

    return await pw_run(_launch())


async def shutdown_browser() -> None:
    async def _shutdown() -> None:
        global _pw, _browser
        for run_id in list(_sessions):
            await close_session(run_id)
        if _browser is not None:
            try:
                await _browser.close()
            except Exception:  # pragma: no cover - teardown best-effort
                pass
            _browser = None
        if _pw is not None:
            try:
                await _pw.stop()
            except Exception:  # pragma: no cover
                pass
            _pw = None

    await pw_run(_shutdown())
    await shutdown_pw_loop()


@dataclass
class BrowserSession:
    run_id: str
    context: BrowserContext
    page: Page
    allowlist: set[str]
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)

    # Run-scoped observation buffers (appended by listeners, drained per step).
    console_errors: list[dict] = field(default_factory=list)
    page_errors: list[dict] = field(default_factory=list)
    failed_requests: list[dict] = field(default_factory=list)
    http_errors: list[dict] = field(default_factory=list)
    offdomain_redirects: list[str] = field(default_factory=list)
    _drained: dict[str, int] = field(default_factory=lambda: {
        "console_errors": 0, "page_errors": 0, "failed_requests": 0, "http_errors": 0,
        "offdomain_redirects": 0,
    })

    # Which URLs already got the once-per-page checks (axe, links, images).
    scanned_urls: set[str] = field(default_factory=set)
    visited_urls: set[str] = field(default_factory=set)
    # Status of the last main-document response (auth-wall detection).
    last_main_status: int | None = None

    def touch(self) -> None:
        self.last_used = time.time()

    def drain_new(self, buffer_name: str) -> list[Any]:
        buf = getattr(self, buffer_name)
        start = self._drained[buffer_name]
        self._drained[buffer_name] = len(buf)
        return buf[start:]

    @staticmethod
    def normalize_url(url: str) -> str:
        return urldefrag(url)[0].rstrip("/")


def _attach_listeners(session: BrowserSession) -> None:
    page = session.page

    def on_console(msg) -> None:
        if msg.type in ("error", "warning"):
            session.console_errors.append(
                {"type": msg.type, "text": msg.text[:500], "page_url": page.url}
            )

    def on_pageerror(err) -> None:
        session.page_errors.append({"text": str(err)[:500], "page_url": page.url})

    def on_requestfailed(req) -> None:
        # Ignore aborts we caused ourselves (allowlist route guard).
        failure = req.failure or ""
        if "ERR_ABORTED" in failure and not safety.is_allowed(req.url, session.allowlist):
            return
        session.failed_requests.append(
            {"url": req.url[:300], "method": req.method, "failure": failure[:200],
             "page_url": page.url}
        )

    def on_response(resp) -> None:
        if resp.status >= 400:
            session.http_errors.append(
                {"url": resp.url[:300], "status": resp.status, "page_url": page.url}
            )
        # Track the main document's status for auth-wall detection.
        try:
            if resp.request.is_navigation_request() and resp.frame == page.main_frame:
                session.last_main_status = resp.status
        except Exception:  # pragma: no cover - frame may be detached
            pass

    def on_framenavigated(frame) -> None:
        # JS-initiated redirects can slip past the navigate tool's check —
        # record off-domain landings as findings-to-be; the observe node acts.
        if frame != page.main_frame:
            return
        url = frame.url
        if url.startswith("http") and not safety.is_allowed(url, session.allowlist):
            session.offdomain_redirects.append(url)

    page.on("console", on_console)
    page.on("pageerror", on_pageerror)
    page.on("requestfailed", on_requestfailed)
    page.on("response", on_response)
    page.on("framenavigated", on_framenavigated)


async def _route_guard(session: BrowserSession, route) -> None:
    """Abort off-allowlist NAVIGATION requests; subresources (CDNs, fonts)
    pass so pages still render."""
    req = route.request
    if req.is_navigation_request() and req.url.startswith("http") \
            and not safety.is_allowed(req.url, session.allowlist):
        await route.abort()
        return
    await route.continue_()


async def create_session(run_id: str, start_url: str) -> BrowserSession:
    """New isolated context+page for a run, with observers + allowlist armed."""

    async def _create() -> BrowserSession:
        await reap_idle_sessions()
        settings = get_settings()
        browser = await get_browser()
        context = await browser.new_context(
            viewport={"width": settings.viewport_width, "height": settings.viewport_height},
        )
        context.set_default_timeout(settings.action_timeout_ms)
        context.set_default_navigation_timeout(settings.nav_timeout_ms)
        page = await context.new_page()

        allowlist = safety.build_allowlist(start_url, settings.allowlist_extra_hosts)
        session = BrowserSession(run_id=run_id, context=context, page=page, allowlist=allowlist)
        _attach_listeners(session)
        await context.route("**/*", lambda route: _route_guard(session, route))

        _sessions[run_id] = session
        logger.info("[browser] session %s created (allowlist=%s)", run_id, sorted(allowlist))
        return session

    return await pw_run(_create())


def get_session(run_id: str) -> BrowserSession | None:
    session = _sessions.get(run_id)
    if session:
        session.touch()
    return session


async def close_session(run_id: str) -> None:
    async def _close() -> None:
        session = _sessions.pop(run_id, None)
        if session is None:
            return
        try:
            await session.context.close()
        except Exception:  # pragma: no cover - already gone
            pass
        logger.info("[browser] session %s closed", run_id)

    await pw_run(_close())


async def reap_idle_sessions() -> None:
    """Close sessions idle past the reap window (paused runs someone forgot)."""
    settings = get_settings()
    cutoff = time.time() - settings.session_idle_reap_s
    for run_id, session in list(_sessions.items()):
        if session.last_used < cutoff:
            logger.info("[browser] reaping idle session %s", run_id)
            await close_session(run_id)
