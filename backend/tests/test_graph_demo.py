"""@browser test: the WHOLE agent loop (observe→decide→act→verify + report
assembly) over the local demo site, with the decide LLM call STUBBED by a
canned script — so it proves the loop end to end with zero API calls.

Run with:  pytest -m browser
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.browser

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402

from app.agent import graph as gmod  # noqa: E402
from app.browser import session as bsession  # noqa: E402
from tests.conftest_browser import DemoServer  # noqa: E402


async def _collect_report(g, initial):
    """Drive the graph and return the emitted `report` event's data."""
    config = {"configurable": {"thread_id": initial["run_id"]}, "recursion_limit": 60}
    report = None
    async for mode, chunk in g.astream(initial, config, stream_mode=["custom", "updates"]):
        if mode == "custom" and chunk.get("type") == "report":
            report = chunk["data"]
    return report


@pytest.fixture
async def demo():
    with DemoServer() as srv:
        yield srv
    await bsession.shutdown_browser()


async def test_full_loop_catches_total_bug(demo, monkeypatch):
    # Canned decide script: add item, verify count (passes), verify total
    # (FAILS — the planted bug), then finish 'fail'.
    script = [
        '{"thought":"add the widget","action":{"tool":"click","args":{"role":"button","name":"Add Widget"}}}',
        '{"thought":"count should be 1","action":{"tool":"assert_text","args":{"text":"Cart items: 1"}}}',
        '{"thought":"total should be $5.00","action":{"tool":"assert_text","args":{"text":"Total: $5.00"}}}',
        '{"thought":"the total never updated","finish":{"verdict":"fail","summary":"Adding an item updates the count but not the total.",'
        '"failures":[{"title":"Cart total does not update","expected":"Total shows $5.00 after adding the $5 widget",'
        '"actual":"Total stayed $0.00","role":"generic","name":"Total"}]}}',
    ]
    calls = {"n": 0}

    async def fake_vision(messages):
        i = min(calls["n"], len(script) - 1)
        calls["n"] += 1
        return script[i]

    monkeypatch.setattr(gmod, "_vision", fake_vision)
    # Skip the auditor LLM in verify — the code-driven verdict is what we test.
    async def fake_audit(scenario, log, findings):
        return {}
    monkeypatch.setattr(gmod, "_audit", fake_audit)

    g = gmod.build_graph(MemorySaver())
    report = await _collect_report(g, {
        "run_id": "graph-test-1",
        "scenario": "Add an item to the cart; the total must update to reflect it.",
        "start_url": demo.base + "/demo/shop.html",
        "step": 0, "max_steps": 8,
    })
    await bsession.close_session("graph-test-1")

    assert report is not None, "no report event emitted"
    assert report["verdict"] == "fail"
    cats = {f["category"] for f in report["findings"]}
    assert "functional" in cats
    # the functional finding should have screenshot evidence attached
    func = next(f for f in report["findings"] if f["category"] == "functional")
    assert func["evidence"] is not None
    assert report["stats"]["steps"] >= 3


async def test_full_loop_clean_page_passes(demo, monkeypatch):
    # On the clean page, the agent just verifies the heading and finishes 'pass'.
    script = [
        '{"thought":"the page looks healthy","action":{"tool":"assert_visible","args":{"text":"A Perfectly Healthy Page"}}}',
        '{"thought":"all good","finish":{"verdict":"pass","summary":"The page is healthy.","failures":[]}}',
    ]
    calls = {"n": 0}

    async def fake_vision(messages):
        i = min(calls["n"], len(script) - 1)
        calls["n"] += 1
        return script[i]

    monkeypatch.setattr(gmod, "_vision", fake_vision)
    monkeypatch.setattr(gmod, "_audit", lambda *a: _empty())

    g = gmod.build_graph(MemorySaver())
    report = await _collect_report(g, {
        "run_id": "graph-test-2",
        "scenario": "The page should be healthy with no broken images or errors.",
        "start_url": demo.base + "/demo/clean.html",
        "step": 0, "max_steps": 8,
    })
    await bsession.close_session("graph-test-2")

    assert report is not None
    assert report["verdict"] == "pass"
    # No functional findings on the clean page (the precision control).
    assert not any(f["category"] == "functional" for f in report["findings"])


async def _empty():
    return {}
