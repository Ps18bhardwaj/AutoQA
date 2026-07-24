"""Phase-1 go/no-go gate: prove the whole browser observation stack works
on THIS machine before any agent code is written.

Launches headless Chromium (async API — the only one usable inside FastAPI),
navigates to example.com, and exercises every observation primitive the agent
will rely on:
  1. ARIA snapshot   (page.locator("body").aria_snapshot() — the deprecated
                      page.accessibility.snapshot() is NOT used)
  2. Screenshot      (bytes -> smoke_screenshot.png next to this script)
  3. axe-core scan   (vendored axe.min.js injected via add_script_tag)
  4. Console/network listeners attach without error

    python scripts/smoke_browser.py [--url https://example.com]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright  # noqa: E402

from app.config import get_settings  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://example.com")
    args = ap.parse_args()
    settings = get_settings()

    axe_path = settings.axe_js_path
    if not axe_path.is_file():
        print(f"FAIL: axe.min.js missing at {axe_path}")
        return 1

    t0 = time.perf_counter()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        print(f"[1/5] Chromium launched in {time.perf_counter() - t0:.1f}s")

        context = await browser.new_context(
            viewport={"width": settings.viewport_width, "height": settings.viewport_height},
        )
        page = await context.new_page()

        console_msgs: list[str] = []
        failed_reqs: list[str] = []
        page.on("console", lambda m: console_msgs.append(f"{m.type}: {m.text}"))
        page.on("requestfailed", lambda r: failed_reqs.append(r.url))
        print("[2/5] Console/network listeners attached")

        await page.goto(args.url, timeout=settings.nav_timeout_ms)
        title = await page.title()

        snapshot = await page.locator("body").aria_snapshot()
        lines = snapshot.splitlines()
        print(f"[3/5] ARIA snapshot of {args.url!r} (title={title!r}) — "
              f"{len(lines)} lines, first {min(20, len(lines))}:")
        for line in lines[:20]:
            print(f"      {line}")

        shot = await page.screenshot()
        out = Path(__file__).parent / "smoke_screenshot.png"
        out.write_bytes(shot)
        print(f"[4/5] Screenshot: {len(shot) / 1024:.0f}KB -> {out.name}")

        await page.add_script_tag(path=str(axe_path))
        results = await page.evaluate("async () => await axe.run()")
        violations = results.get("violations", [])
        print(f"[5/5] axe-core scan: {len(violations)} violation(s)"
              + (f" — e.g. {violations[0]['id']}: {violations[0]['help']}" if violations else ""))

        await browser.close()

    print(f"\nPASS — full observation stack works ({time.perf_counter() - t0:.1f}s total). "
          f"({len(console_msgs)} console msgs, {len(failed_reqs)} failed requests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
