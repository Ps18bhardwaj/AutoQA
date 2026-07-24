"""@browser tests: real Chromium against the local demo site, NO LLM.

Exercises the tool layer, the observer buffers, axe, and annotation against
pages with deterministic planted bugs. Auto-skips if Chromium isn't installed.
Run with:  pytest -m browser
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.browser

from app.browser import annotate, checks, session as bsession, tools  # noqa: E402
from tests.conftest_browser import DemoServer  # noqa: E402


@pytest.fixture
async def demo():
    with DemoServer() as srv:
        yield srv


@pytest.fixture
async def sess(demo):
    s = await bsession.create_session("test-run", demo.base + "/demo/index.html")
    try:
        yield s, demo
    finally:
        await bsession.close_session("test-run")
        await bsession.shutdown_browser()


async def test_navigate_and_aria_snapshot(sess):
    s, demo = sess
    reg = tools.build_registry()
    obs = await reg["navigate"].run(s, {"url": demo.base + "/demo/index.html"})
    assert "Navigated" in obs and "AutoQA Demo" in obs
    snap = await s.page.locator("body").aria_snapshot()
    assert "AutoQA Demo Site" in snap


async def test_observers_capture_planted_console_and_network_bugs(sess):
    s, demo = sess
    reg = tools.build_registry()
    await reg["navigate"].run(s, {"url": demo.base + "/demo/index.html"})
    await s.page.wait_for_timeout(600)  # let the on-load fetch + console fire
    console = s.drain_new("console_errors")
    http = s.drain_new("http_errors")
    assert any("planted" in c["text"] for c in console), console
    assert any(e["status"] == 404 for e in http), http


async def test_broken_image_detected(sess):
    s, demo = sess
    reg = tools.build_registry()
    await reg["navigate"].run(s, {"url": demo.base + "/demo/index.html"})
    await s.page.wait_for_timeout(400)
    findings = await checks.broken_image_findings(s.page, [0])
    assert any("does-not-exist" in f.actual for f in findings), findings


async def test_axe_finds_planted_a11y_violations(sess):
    s, demo = sess
    reg = tools.build_registry()
    await reg["navigate"].run(s, {"url": demo.base + "/demo/index.html"})
    violations = await checks.run_axe(s.page)
    ids = {v["id"] for v in violations}
    # planted: low-contrast text -> color-contrast
    assert "color-contrast" in ids, ids


async def test_clean_page_has_no_broken_images_or_console(sess):
    s, demo = sess
    reg = tools.build_registry()
    await reg["navigate"].run(s, {"url": demo.base + "/demo/clean.html"})
    await s.page.wait_for_timeout(400)
    assert await checks.broken_image_findings(s.page, [0]) == []
    assert s.drain_new("console_errors") == []


async def test_shop_total_bug_via_assert_tool(sess):
    s, demo = sess
    reg = tools.build_registry()
    await reg["navigate"].run(s, {"url": demo.base + "/demo/shop.html"})
    # Add an item; the count updates but the total stays $0.00 (planted bug).
    click_obs = await reg["click"].run(s, {"role": "button", "name": "Add Widget"})
    assert "Clicked" in click_obs, click_obs
    passed = await reg["assert_text"].run(s, {"text": "Cart items: 1"})
    assert passed.startswith("ASSERTION PASSED")
    failed = await reg["assert_text"].run(s, {"text": "Total: $5.00"})
    assert failed.startswith("ASSERTION FAILED"), failed


async def test_click_refuses_form_submit_control(sess):
    s, demo = sess
    reg = tools.build_registry()
    await reg["navigate"].run(s, {"url": demo.base + "/demo/shop.html"})
    obs = await reg["click"].run(s, {"role": "button", "name": "Place order"})
    assert obs.startswith("ERROR: that control submits a form")


async def test_navigate_offdomain_is_blocked(sess):
    s, demo = sess
    reg = tools.build_registry()
    obs = await reg["navigate"].run(s, {"url": "https://www.google.com"})
    assert obs.startswith("ERROR: navigation to") and "outside the allowed" in obs


async def test_annotate_box_produces_valid_png(sess):
    s, demo = sess
    reg = tools.build_registry()
    await reg["navigate"].run(s, {"url": demo.base + "/demo/shop.html"})
    loc = s.page.get_by_role("button", name="Add Widget").first
    box = await loc.bounding_box()
    png = await s.page.screenshot()
    boxed = annotate.box_element(png, box)
    assert boxed[:8] == b"\x89PNG\r\n\x1a\n"        # PNG magic
    assert len(boxed) >= len(png) - 100             # drawing shouldn't shrink it materially
