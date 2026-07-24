"""Keyless tests for decide_node's routing guards — the branches that keep the
agent from spinning the decide->decide edge to the recursion limit. The vision
LLM is stubbed; several branches return before it's ever called."""
import pytest

from app.agent import graph as gmod


def _state(**kw):
    base = {"run_id": "t", "scenario": "check the page", "start_url": "http://x",
            "step": 1, "max_steps": 12, "scratchpad": [],
            "last_snapshot": "- heading: Hi", "last_screenshot_b64": "data:image/jpeg;base64,x",
            "findings": []}
    base.update(kw)
    return base


async def test_blocked_reason_finishes_blocked_without_llm(monkeypatch):
    called = {"n": 0}
    async def boom(_): called["n"] += 1; return "{}"
    monkeypatch.setattr(gmod, "_vision", boom)
    out = await gmod.decide_node(_state(blocked_reason="a captcha was detected"))
    assert out["forced_finish"] and out["finish"]["verdict"] == "blocked"
    assert called["n"] == 0  # never consulted the model


async def test_step_limit_finishes_without_llm(monkeypatch):
    async def boom(_): raise AssertionError("LLM should not be called at the step limit")
    monkeypatch.setattr(gmod, "_vision", boom)
    out = await gmod.decide_node(_state(step=12, max_steps=12))
    assert out["forced_finish"] and out["finish"]["verdict"] == "fail"


async def test_nudge_cap_force_finishes(monkeypatch):
    """4 accumulated nudges → force finish instead of re-deciding forever."""
    async def boom(_): raise AssertionError("LLM should not be called past the nudge cap")
    monkeypatch.setattr(gmod, "_vision", boom)
    scratch = [{"tool": "_nudge", "args": {}, "observation": "x"} for _ in range(4)]
    out = await gmod.decide_node(_state(scratchpad=scratch))
    assert out["forced_finish"] and out["finish"]["verdict"] == "fail"


async def test_unknown_tool_returns_nudge_not_pending(monkeypatch):
    async def fake(_): return '{"thought":"t","action":{"tool":"teleport","args":{}}}'
    monkeypatch.setattr(gmod, "_vision", fake)
    out = await gmod.decide_node(_state())
    # a nudge is appended, no action is dispatched, and we don't force-finish yet
    assert "pending" not in out or out.get("pending") is None
    assert out["scratchpad"][-1]["tool"] == "_nudge"
    assert not out.get("forced_finish")


async def test_repeated_action_thrice_force_finishes(monkeypatch):
    async def fake(_): return '{"thought":"again","action":{"tool":"click","args":{"role":"button","name":"X"}}}'
    monkeypatch.setattr(gmod, "_vision", fake)
    # the same click already ran twice → this 3rd attempt must force finish
    scratch = [{"tool": "click", "args": {"role": "button", "name": "X"}, "observation": "ok"},
               {"tool": "click", "args": {"role": "button", "name": "X"}, "observation": "ok"}]
    out = await gmod.decide_node(_state(scratchpad=scratch))
    assert out["forced_finish"] and out["finish"]["verdict"] == "fail"


async def test_first_repeat_is_allowed_through(monkeypatch):
    async def fake(_): return '{"thought":"retry","action":{"tool":"click","args":{"role":"button","name":"X"}}}'
    monkeypatch.setattr(gmod, "_vision", fake)
    scratch = [{"tool": "click", "args": {"role": "button", "name": "X"}, "observation": "ok"}]
    out = await gmod.decide_node(_state(scratchpad=scratch))
    # one prior repeat → allowed to run (pending set), not force-finished
    assert out.get("pending", {}).get("tool") == "click"
    assert not out.get("forced_finish")


async def test_normal_action_sets_pending(monkeypatch):
    async def fake(_): return '{"thought":"go","action":{"tool":"click","args":{"role":"link","name":"Home"}}}'
    monkeypatch.setattr(gmod, "_vision", fake)
    out = await gmod.decide_node(_state())
    assert out["pending"]["tool"] == "click"
    assert out["pending"]["args"] == {"role": "link", "name": "Home"}


async def test_finish_pass_with_no_actions_is_nudged(monkeypatch):
    async def fake(_): return '{"thought":"done","finish":{"verdict":"pass","summary":"ok","failures":[]}}'
    monkeypatch.setattr(gmod, "_vision", fake)
    out = await gmod.decide_node(_state(scratchpad=[]))
    # premature 'pass' with nothing done → nudge, not a finish
    assert "finish" not in out
    assert out["scratchpad"][-1]["tool"] == "_nudge"
