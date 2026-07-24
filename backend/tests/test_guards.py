"""Keyless tests for the pure agent guards (parse_json, loop, no-progress)."""
import json

from app.agent import guards


def test_parse_json_plain():
    assert guards.parse_json('{"a": 1}') == {"a": 1}


def test_parse_json_fenced():
    assert guards.parse_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_with_prose():
    assert guards.parse_json('Sure!\n{"action": {"tool": "click"}}\nDone') == {"action": {"tool": "click"}}


def test_parse_json_garbage_returns_empty():
    assert guards.parse_json("no json here") == {}
    assert guards.parse_json("") == {}


def _step(tool, args):
    return {"tool": tool, "args": args, "observation": "x"}


def test_detect_action_loop_counts_identical():
    pad = [_step("click", {"role": "button", "name": "X"}),
           _step("scroll", {"direction": "down"}),
           _step("click", {"role": "button", "name": "X"})]
    # same click appears twice already
    assert guards.detect_action_loop(pad, "click", {"role": "button", "name": "X"}) == 2
    # a different action hasn't appeared
    assert guards.detect_action_loop(pad, "click", {"role": "button", "name": "Y"}) == 0


def test_detect_action_loop_respects_window():
    pad = [_step("click", {"n": 1})] + [_step("scroll", {"direction": "down"}) for _ in range(6)]
    # the old click falls outside the 6-step window
    assert guards.detect_action_loop(pad, "click", {"n": 1}, window=6) == 0


def test_detect_action_loop_ignores_arg_order():
    pad = [_step("type_text", {"role": "textbox", "name": "N", "text": "hi"})]
    assert guards.detect_action_loop(pad, "type_text", {"text": "hi", "name": "N", "role": "textbox"}) == 1


def test_no_progress_true_when_hashes_identical():
    h = guards.snapshot_hash("same", "http://x")
    assert guards.detect_no_progress([h, h, h, h]) is True


def test_no_progress_false_when_changing():
    hashes = [guards.snapshot_hash(f"s{i}", "http://x") for i in range(4)]
    assert guards.detect_no_progress(hashes) is False


def test_no_progress_false_below_threshold():
    h = guards.snapshot_hash("same", "http://x")
    assert guards.detect_no_progress([h, h]) is False


def test_snapshot_hash_depends_on_url():
    assert guards.snapshot_hash("s", "http://a") != guards.snapshot_hash("s", "http://b")
