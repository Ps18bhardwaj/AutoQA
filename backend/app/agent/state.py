"""The AutoQA agent's graph state.

Deliberately holds only JSON-serializable data — NO Playwright objects (the
checkpointer would choke, and they can't cross request tasks). The live
browser lives in ``browser.session`` keyed by ``run_id``; every node looks it
up. Findings accumulate as plain dicts and are turned into the typed
``Report`` at the end.
"""
from __future__ import annotations

from typing import Any

from typing_extensions import TypedDict


class Step(TypedDict, total=False):
    step: int
    thought: str
    tool: str
    args: dict[str, Any]
    observation: str
    page_url: str
    ok: bool


class QAState(TypedDict, total=False):
    run_id: str
    scenario: str
    start_url: str

    step: int
    max_steps: int
    scratchpad: list[Step]           # observe/decide/act history

    last_snapshot: str               # ARIA snapshot text from the latest observe
    last_screenshot_url: str         # /runs/{id}/step_{n}.png
    last_screenshot_b64: str         # JPEG data-URL for the decide vision call

    findings: list[dict]             # accumulating Finding dicts (auto + scenario)
    blocked_reason: str | None

    pending: dict | None             # chosen action awaiting act/approval
    finish: dict | None              # decide's {verdict, summary, failures[]}
    forced_finish: bool              # step limit / loop-detector escalation

    verdict: str                     # set by verify: pass | fail | blocked
    started_at: float
