"""Pure, I/O-free decision guards for the agent loop — unit-tested keyless.

  * parse_json          — best-effort JSON extraction from an LLM reply
  * detect_action_loop  — same (tool,args) repeated too often
  * detect_no_progress  — page unchanged across several steps (infinite-scroll spin)
"""
from __future__ import annotations

import hashlib
import json

from ..browser.tools import canonical_args


def parse_json(text: str) -> dict:
    """Extract a JSON object from an LLM response (strips fences / prose)."""
    if not text:
        return {}
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[4:] if t.lower().startswith("json") else t
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {}
    try:
        return json.loads(t[start:end + 1])
    except json.JSONDecodeError:
        return {}


def _action_key(tool: str, args: dict) -> str:
    return f"{tool}::{canonical_args(args or {})}"


def detect_action_loop(scratchpad: list[dict], tool: str, args: dict, *, window: int = 6) -> int:
    """How many times this exact (tool, args) already appears in the last
    `window` action steps. Caller escalates: 1 prior → nudge, 2 prior → force
    finish (so the current attempt would be the 2nd / 3rd occurrence)."""
    key = _action_key(tool, args)
    recent = [s for s in scratchpad if s.get("tool")][-window:]
    return sum(1 for s in recent if _action_key(s.get("tool", ""), s.get("args", {})) == key)


def snapshot_hash(snapshot: str, url: str) -> str:
    return hashlib.sha1(f"{url}\n{snapshot}".encode("utf-8", "replace")).hexdigest()


def detect_no_progress(recent_hashes: list[str], *, threshold: int = 4) -> bool:
    """True if the last `threshold` observe steps produced an identical
    (url, snapshot) hash — the page isn't changing no matter what we do."""
    if len(recent_hashes) < threshold:
        return False
    tail = recent_hashes[-threshold:]
    return len(set(tail)) == 1
