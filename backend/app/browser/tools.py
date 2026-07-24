"""The typed, whitelisted browser action set — AutoQA's entire action surface.

Same contract as TaskPilot's tool registry: every action is a ``Tool`` with a
``run(session, args) -> str`` that NEVER raises. Failures (bad selector,
timeout, off-allowlist nav, refused credential) come back as ``"ERROR: ..."``
observation strings the agent reads and adapts to. ``ASSERTION FAILED: ...``
strings become functional findings in the report.

Safety is baked into the tools, not bolted on:
  * navigate  — allowlist-enforced
  * click     — refuses form-submit controls (points at the approval-gated `submit`)
  * type_text — credential guard (never types real passwords / payment data)
  * submit    — the ONLY write=True tool → human approval before it runs
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable
from urllib.parse import urlparse

from playwright.async_api import Error as PWError, TimeoutError as PWTimeout

from ..config import get_settings
from .. import safety
from ._pw_loop import run as pw_run
from .session import BrowserSession

logger = logging.getLogger("autoqa.tools")

_ALLOWED_KEYS = {"Enter", "Escape", "Tab", "ArrowDown", "ArrowUp"}


@dataclass
class Tool:
    name: str
    description: str
    args_hint: str
    write: bool
    run: Callable[[BrowserSession, dict], Awaitable[str]]
    schema: dict | None = None


# --------------------------------------------------------------------------
# Element resolution — role/name grounded in the ARIA snapshot the LLM saw.
# --------------------------------------------------------------------------
async def _resolve(session: BrowserSession, args: dict):
    """Return (locator, None) or (None, error_string). Text-first, dynamic-
    selector-resilient targeting: role+name copied from the snapshot, with a
    get_by_text fallback."""
    page = session.page
    role = (args.get("role") or "").strip()
    name = (args.get("name") or "").strip()
    settings = get_settings()

    if role and name:
        loc = page.get_by_role(role, name=name, exact=False).first
        try:
            await loc.wait_for(state="visible", timeout=settings.action_timeout_ms)
            return loc, None
        except PWTimeout:
            pass  # fall through to text fallback
    if name:
        loc = page.get_by_text(name, exact=False).first
        try:
            await loc.wait_for(state="visible", timeout=2000)
            return loc, None
        except PWTimeout:
            pass
    return None, (f"ERROR: no visible element with role={role!r} name={name!r}. "
                  f"Re-read the PAGE SNAPSHOT and use an exact role+name from it.")


# --------------------------------------------------------------------------
# Actions
# --------------------------------------------------------------------------
async def _navigate(session: BrowserSession, args: dict) -> str:
    url = (args.get("url") or "").strip()
    if not url:
        return "ERROR: navigate requires a 'url'."
    if not url.startswith("http"):
        url = "https://" + url
    if not safety.is_allowed(url, session.allowlist):
        host = urlparse(url).hostname
        return (f"ERROR: navigation to {host!r} is outside the allowed domain(s) "
                f"{sorted(session.allowlist)}. AutoQA stays on the site under test.")
    settings = get_settings()
    try:
        resp = await session.page.goto(url, timeout=settings.nav_timeout_ms)
        status = resp.status if resp else "?"
        return f"Navigated to {session.page.url} (HTTP {status}). Title: {await session.page.title()!r}"
    except PWTimeout:
        return f"ERROR: page load timed out after {settings.nav_timeout_ms // 1000}s at {url}"
    except PWError as e:
        return f"ERROR: navigation failed: {str(e)[:150]}"


async def _is_submit_control(loc) -> bool:
    try:
        return await loc.evaluate(
            """el => !!el.closest('form') &&
                (el.type === 'submit' ||
                 (el.tagName === 'BUTTON' && el.type !== 'button' && el.type !== 'reset'))"""
        )
    except PWError:  # pragma: no cover - element detached
        return False


async def _click(session: BrowserSession, args: dict) -> str:
    loc, err = await _resolve(session, args)
    if err:
        return err
    if await _is_submit_control(loc):
        return ("ERROR: that control submits a form — use the `submit` tool "
                "(it requires human approval). `click` is for non-submitting elements.")
    try:
        await loc.click(timeout=get_settings().action_timeout_ms)
        return f"Clicked {args.get('role')} {args.get('name')!r}. Now at {session.page.url}"
    except PWError as e:
        return f"ERROR: click failed: {str(e)[:150]}"


async def _type_text(session: BrowserSession, args: dict) -> str:
    loc, err = await _resolve(session, args)
    if err:
        return err
    value = args.get("text", "")
    settings = get_settings()
    try:
        is_password = await loc.evaluate("el => el.type === 'password'")
    except PWError:
        is_password = False
    host = (urlparse(session.page.url).hostname or "").lower()
    verdict = safety.credential_verdict(
        value=value, field_name=args.get("name", ""), is_password_input=bool(is_password),
        page_host=host, known_test_hosts=settings.known_test_host_list,
        test_credentials=settings.test_credential_list,
    )
    if verdict:
        return verdict
    try:
        await loc.fill(value, timeout=settings.action_timeout_ms)
        shown = "•" * len(value) if is_password else value
        return f"Typed {shown!r} into {args.get('role')} {args.get('name')!r}."
    except PWError as e:
        return f"ERROR: type failed: {str(e)[:150]}"


async def _press_key(session: BrowserSession, args: dict) -> str:
    key = args.get("key", "")
    if key not in _ALLOWED_KEYS:
        return f"ERROR: key must be one of {sorted(_ALLOWED_KEYS)}."
    try:
        await session.page.keyboard.press(key)
        return f"Pressed {key}. Now at {session.page.url}"
    except PWError as e:
        return f"ERROR: press failed: {str(e)[:150]}"


async def _select_option(session: BrowserSession, args: dict) -> str:
    loc, err = await _resolve(session, args)
    if err:
        return err
    try:
        await loc.select_option(label=args.get("value"))
        return f"Selected {args.get('value')!r} in {args.get('name')!r}."
    except PWError:
        try:
            await loc.select_option(value=args.get("value"))
            return f"Selected {args.get('value')!r} in {args.get('name')!r}."
        except PWError as e:
            return f"ERROR: select failed: {str(e)[:150]}"


async def _scroll(session: BrowserSession, args: dict) -> str:
    direction = args.get("direction", "down")
    dy = session.page.viewport_size["height"] if direction == "down" else -session.page.viewport_size["height"]
    try:
        before = await session.page.evaluate("() => document.body.scrollHeight")
        await session.page.mouse.wheel(0, dy)
        await session.page.wait_for_timeout(400)  # let lazy content load
        after = await session.page.evaluate("() => document.body.scrollHeight")
        if direction == "down" and after == before:
            return "Scrolled down; page height unchanged — likely the end of content."
        return f"Scrolled {direction} (page height {before} -> {after})."
    except PWError as e:
        return f"ERROR: scroll failed: {str(e)[:150]}"


async def _go_back(session: BrowserSession, args: dict) -> str:
    try:
        await session.page.go_back(timeout=get_settings().nav_timeout_ms)
        return f"Went back. Now at {session.page.url}"
    except PWError as e:
        return f"ERROR: go_back failed: {str(e)[:150]}"


async def _assert_visible(session: BrowserSession, args: dict) -> str:
    # Supports {role, name} OR a plain {text}.
    text = args.get("text")
    if text and not args.get("name"):
        loc = session.page.get_by_text(text, exact=False).first
        try:
            await loc.wait_for(state="visible", timeout=get_settings().action_timeout_ms)
            return f"ASSERTION PASSED: {text!r} is visible."
        except PWTimeout:
            return f"ASSERTION FAILED: expected {text!r} to be visible, but it was not found."
    loc, err = await _resolve(session, args)
    label = args.get("name") or text or "?"
    if err:
        return f"ASSERTION FAILED: expected {label!r} to be visible, but it was not found."
    return f"ASSERTION PASSED: {label!r} is visible."


async def _assert_text(session: BrowserSession, args: dict) -> str:
    text = args.get("text", "")
    try:
        body = await session.page.locator("body").inner_text(timeout=get_settings().action_timeout_ms)
    except PWError as e:
        return f"ASSERTION FAILED: could not read page text ({str(e)[:80]})."
    if text.lower() in body.lower():
        return f"ASSERTION PASSED: page contains {text!r}."
    return f"ASSERTION FAILED: page does NOT contain {text!r}."


async def _submit(session: BrowserSession, args: dict) -> str:
    # Only runs AFTER human approval (write=True → approval gate in the graph).
    loc, err = await _resolve(session, args)
    if err:
        return err
    try:
        await loc.click(timeout=get_settings().action_timeout_ms)
        return f"Submitted via {args.get('name')!r}. Now at {session.page.url}"
    except PWError as e:
        return f"ERROR: submit failed: {str(e)[:150]}"


def _schema(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}


_STR = {"type": "string"}


def _on_pw_loop(fn: Callable[[BrowserSession, dict], Awaitable[str]]):
    """Run tool coroutines on the Playwright event-loop thread."""
    async def wrapped(session: BrowserSession, args: dict) -> str:
        async def work() -> str:
            return await fn(session, args)
        return await pw_run(work())
    return wrapped


def build_registry() -> dict[str, Tool]:
    tools = [
        Tool("navigate", "Load a URL (must be on the allowed domain).",
             "{url}", False, _on_pw_loop(_navigate), _schema({"url": _STR}, ["url"])),
        Tool("click", "Click a non-submitting element by its accessible role+name.",
             "{role, name}", False, _on_pw_loop(_click), _schema({"role": _STR, "name": _STR}, ["role", "name"])),
        Tool("type_text", "Type text into a field by role+name (never real credentials).",
             "{role, name, text}", False, _on_pw_loop(_type_text),
             _schema({"role": _STR, "name": _STR, "text": _STR}, ["role", "name", "text"])),
        Tool("press_key", "Press one key: Enter/Escape/Tab/ArrowDown/ArrowUp.",
             "{key}", False, _on_pw_loop(_press_key), _schema({"key": _STR}, ["key"])),
        Tool("select_option", "Choose an option in a <select> by role+name.",
             "{role, name, value}", False, _on_pw_loop(_select_option),
             _schema({"role": _STR, "name": _STR, "value": _STR}, ["role", "name", "value"])),
        Tool("scroll", "Scroll one viewport up or down.",
             "{direction}", False, _on_pw_loop(_scroll), _schema({"direction": _STR}, ["direction"])),
        Tool("go_back", "Navigate back in history.", "{}", False, _on_pw_loop(_go_back), _schema({}, [])),
        Tool("assert_visible", "Check an element is visible (role+name or text).",
             "{role?, name?, text?}", False, _on_pw_loop(_assert_visible),
             _schema({"role": _STR, "name": _STR, "text": _STR}, [])),
        Tool("assert_text", "Check the page contains some text.",
             "{text}", False, _on_pw_loop(_assert_text), _schema({"text": _STR}, ["text"])),
        Tool("submit", "Submit a form (REQUIRES HUMAN APPROVAL).",
             "{role, name}", True, _on_pw_loop(_submit), _schema({"role": _STR, "name": _STR}, ["role", "name"])),
    ]
    return {t.name: t for t in tools}


def needs_approval(tool_name: str, args: dict) -> bool:
    """Static write=True tools, plus the dynamic case of pressing Enter (which
    can submit a focused form)."""
    if tool_name == "submit":
        return True
    if tool_name == "press_key" and args.get("key") == "Enter":
        return True
    return False


def canonical_args(args: dict) -> str:
    """Stable key for loop detection (same tool + same args twice)."""
    return json.dumps(args, sort_keys=True, ensure_ascii=False)
