"""AutoQA as a LangGraph state machine: observe → decide → act → verify.

    START → bootstrap → observe → decide ─┬─ act ──────────→ observe
                          ▲               ├─ approval ─(ok)─→ act
                          │               │         └(reject)→ decide
                          └───(act)───────┘
                                          └─ (finish|blocked|limit|loop) → verify → END

Design choices that matter in interviews:
  * We build the loop ourselves (no browser-use wrapper) — full control over the
    QA-specific observation stack (ARIA snapshot + axe + console/network capture).
  * Vision-grounded targeting: the model picks {role, name} FROM the snapshot it
    was shown, so it can't hallucinate a CSS selector; text-first = resilient to
    dynamic class/id churn.
  * Safety is layered: domain allowlist, read-only-by-default tools, a human
    approval gate before any form submission, and a credential guard.
  * The final verdict is decided by CODE (report.decide_verdict), not the LLM's
    claim — the auditor LLM can add findings, never launder one away.
"""
from __future__ import annotations

import asyncio
import io
import logging
import time
from base64 import b64encode

import aiosqlite
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from PIL import Image

from ..config import get_settings
from ..llm_compat import chat
from .. import report as report_mod
from ..report import Category, Evidence, Finding, Severity
from .. import safety
from ..browser import annotate, checks, session as bsession
from ..browser._pw_loop import run as pw_run
from ..browser.tools import Tool, build_registry, needs_approval
from . import guards
from .prompts import decide_messages, verify_messages
from .state import QAState

logger = logging.getLogger("autoqa.agent")

_registry: dict[str, Tool] = build_registry()

# Per-run rolling snapshot hashes for the no-progress detector (run_id -> [hash]).
_progress: dict[str, list[str]] = {}


def _emit(etype: str, **data) -> None:
    try:
        writer = get_stream_writer()
    except Exception:
        writer = None
    if writer is not None:
        writer({"type": etype, "data": data})


def _finding_dict(f: Finding) -> dict:
    return f.model_dump(mode="json")


# --------------------------------------------------------------------------
# Screenshot handling
# --------------------------------------------------------------------------
async def _capture(session, run_id: str, step: int) -> tuple[str, str]:
    """Screenshot the page → save PNG to runs/{id}/step_{n}.png (served URL)
    and return (url, jpeg_data_url) — JPEG (downscaled) for the vision call to
    keep the inline payload small."""

    async def work() -> tuple[str, str]:
        settings = get_settings()
        png = await session.page.screenshot()

        run_dir = settings.runs_dir_path / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / f"step_{step:03d}.png").write_bytes(png)
        url = f"/runs/{run_id}/step_{step:03d}.png"

        # PNG -> JPEG q70 for the LLM (well under Gemini's 20MB inline cap).
        try:
            img = Image.open(io.BytesIO(png)).convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=70)
            data_url = "data:image/jpeg;base64," + b64encode(buf.getvalue()).decode()
        except Exception:  # pragma: no cover
            data_url = "data:image/png;base64," + b64encode(png).decode()
        return url, data_url

    return await pw_run(work())


# --------------------------------------------------------------------------
# Nodes
# --------------------------------------------------------------------------
async def bootstrap_node(state: QAState) -> dict:
    run_id, start_url = state["run_id"], state["start_url"]
    _progress[run_id] = []
    _emit("status", phase="starting")
    session = await bsession.create_session(run_id, start_url)

    reg = _registry
    obs = await reg["navigate"].run(session, {"url": start_url})
    _emit("observation", tool="navigate", result=obs)
    entry = {"step": 0, "thought": "Open the start URL", "tool": "navigate",
             "args": {"url": start_url}, "observation": obs, "page_url": session.page.url,
             "ok": not obs.startswith("ERROR")}
    blocked = None if entry["ok"] else "the start URL could not be loaded"
    return {
        "step": 0, "scratchpad": [entry], "findings": [],
        "blocked_reason": blocked, "started_at": time.time(),
    }


async def observe_node(state: QAState) -> dict:
    run_id = state["run_id"]
    session = bsession.get_session(run_id)
    if session is None:
        return {"blocked_reason": "browser session expired"}
    settings = get_settings()
    step = state["step"]
    stream_events: list[tuple[str, dict]] = []

    async def pw_work() -> dict:
        page = session.page

        def emit(etype: str, **data) -> None:
            stream_events.append((etype, data))

        # 1. ARIA snapshot (truncated for the prompt) + screenshot.
        try:
            snapshot = await page.locator("body").aria_snapshot()
        except Exception as e:  # pragma: no cover
            snapshot = f"(snapshot unavailable: {str(e)[:80]})"
        if len(snapshot) > settings.aria_max_chars:
            snapshot = snapshot[:settings.aria_max_chars] + "\n…[snapshot truncated — scroll to see more]"

        shot_url, shot_data = await _capture(session, run_id, step)
        emit("screenshot", step=step, url=shot_url, page_url=page.url,
             title=(await page.title()))

        new_findings: list[dict] = []
        counter = [len(state.get("findings", []))]

        # 2. Once-per-new-URL checks: axe + broken images + capped dead-link sweep.
        norm = session.normalize_url(page.url)
        session.visited_urls.add(norm)
        if norm not in session.scanned_urls:
            session.scanned_urls.add(norm)
            violations = await checks.run_axe(page)
            axe_f = checks.axe_findings(violations, page.url, counter)
            imgs = await checks.broken_image_findings(page, counter)
            links = await checks.dead_link_findings(page, session.allowlist, counter)
            for f in axe_f + imgs + links:
                new_findings.append(_finding_dict(f))
            if axe_f or imgs or links:
                emit("page_check", kind="page", page_url=page.url,
                      count=len(axe_f) + len(imgs) + len(links),
                      preview=[f.title for f in (axe_f + imgs + links)[:5]])

        # 3. Every step: drain console/network buffers into findings.
        console_new = session.drain_new("console_errors")
        pageerr_new = session.drain_new("page_errors")
        failed_new = session.drain_new("failed_requests")
        http_new = session.drain_new("http_errors")
        offdomain_new = session.drain_new("offdomain_redirects")
        for f in checks.console_findings(console_new, counter):
            new_findings.append(_finding_dict(f))
        for f in checks.pageerror_findings(pageerr_new, counter):
            new_findings.append(_finding_dict(f))
        for f in checks.network_findings(failed_new, http_new, counter):
            new_findings.append(_finding_dict(f))
        if console_new or failed_new or http_new:
            emit("page_check", kind="runtime", page_url=page.url,
                  count=len(console_new) + len(failed_new) + len(http_new),
                  preview=[c.get("text", "")[:60] for c in console_new[:3]])
        for url in offdomain_new:
            f = Finding(id=f"f{counter[0]}", severity=Severity.MAJOR, category=Category.FUNCTIONAL,
                        title="Off-domain redirect", expected="Stays on the site under test",
                        actual=f"Page navigated to {url}", page_url=page.url)
            counter[0] += 1
            new_findings.append(_finding_dict(f))

        for fd in new_findings:
            emit("finding", **fd)

        # 4. CAPTCHA / auth-wall detection.
        blocked = safety.detect_block(snapshot, await page.title(), session.last_main_status)

        # 5. No-progress detector (infinite-scroll spin etc.).
        hashes = _progress.setdefault(run_id, [])
        hashes.append(guards.snapshot_hash(snapshot, page.url))

        return {
            "last_snapshot": snapshot,
            "last_screenshot_url": shot_url,
            "last_screenshot_b64": shot_data,
            "findings": state.get("findings", []) + new_findings,
            "blocked_reason": state.get("blocked_reason") or blocked,
        }

    result = await pw_run(pw_work())
    for etype, data in stream_events:
        _emit(etype, **data)
    return result


async def _vision(messages: list[dict]) -> str:
    s = get_settings()
    _emit("status", phase="thinking")
    return await asyncio.to_thread(
        lambda: chat(messages, model=s.vision_model, fallback_model=s.vision_fallback,
                     temperature=0.1, max_tokens=s.decide_max_tokens,
                     metadata={"trace_name": "autoqa-decide"}),
    )


async def decide_node(state: QAState) -> dict:
    step, max_steps = state["step"], state["max_steps"]

    # Pre-LLM routing conditions.
    if state.get("blocked_reason"):
        return {"finish": {"verdict": "blocked", "summary": state["blocked_reason"], "failures": []},
                "forced_finish": True}
    if step >= max_steps:
        _emit("thought", text=f"Reached the {max_steps}-step limit — finishing with what I've verified.")
        return {"finish": {"verdict": "fail", "summary": "Step limit reached before the scenario completed.",
                           "failures": []}, "forced_finish": True}
    if guards.detect_no_progress(_progress.get(state["run_id"], [])):
        _emit("thought", text="The page hasn't changed for several steps — finishing to avoid a loop.")
        return {"finish": {"verdict": "fail", "summary": "The page stopped changing (possible loop).",
                           "failures": []}, "forced_finish": True}
    # Nudge cap: a nudge (bad JSON / unknown tool / premature finish) re-decides
    # WITHOUT running an action or advancing `step`, so the step-limit guard
    # can't catch a nudge storm. Bound it here so a stuck model can't spin the
    # decide→decide edge up to the recursion limit.
    if sum(1 for s in state.get("scratchpad", []) if s.get("tool") == "_nudge") >= 4:
        _emit("thought", text="Too many invalid attempts — finishing.")
        return {"finish": {"verdict": "fail", "summary": "Could not make progress (repeated invalid actions).",
                           "failures": []}, "forced_finish": True}

    messages = decide_messages(state, _registry, state["last_snapshot"], state["last_screenshot_b64"])
    raw = await _vision(messages)
    decision = guards.parse_json(raw)
    if not decision:  # one corrective retry
        messages.append({"role": "user", "content": "That was not valid JSON. Reply with ONLY the JSON object."})
        decision = guards.parse_json(await _vision(messages))

    thought = decision.get("thought", "")
    if thought:
        _emit("thought", text=thought)

    if "finish" in decision:
        # Premature-finish guard: claiming pass with zero actions taken.
        acted = any(s.get("tool") and not s["tool"].startswith(("_", "navigate")) for s in state.get("scratchpad", []))
        fin = decision["finish"]
        if fin.get("verdict") == "pass" and not acted:
            nudge = {"step": step, "tool": "_nudge", "args": {},
                     "observation": "You tried to finish 'pass' without performing or asserting anything. "
                                    "Take an action or run an assertion first."}
            return {"scratchpad": state["scratchpad"] + [nudge]}
        return {"finish": fin}

    action = decision.get("action") or {}
    tool = action.get("tool", "")
    args = action.get("args", {}) or {}
    if tool not in _registry:
        nudge = {"step": step, "tool": "_nudge", "args": {},
                 "observation": f"Unknown tool {tool!r}. Choose one of: {', '.join(_registry)}."}
        return {"scratchpad": state["scratchpad"] + [nudge]}

    # Loop detection: the same (tool, args) already ran twice → force finish
    # (a 3rd identical attempt won't help). A single prior repeat is allowed
    # through as a legitimate retry — executing it advances `step`, so the
    # count strictly rises and termination is guaranteed. (Executing beats a
    # nudge here: a nudge that doesn't run the action never adds to the
    # scratchpad, so the repeat-count would stay stuck and spin the loop.)
    prior = guards.detect_action_loop(state.get("scratchpad", []), tool, args)
    if prior >= 2:
        _emit("thought", text="I've repeated this action too many times — finishing.")
        return {"finish": {"verdict": "fail", "summary": "Repeated the same ineffective action (loop).",
                           "failures": []}, "forced_finish": True}

    _emit("action", tool=tool, args=args, step=step)
    return {"pending": {"tool": tool, "args": args, "thought": thought}}


async def act_node(state: QAState) -> dict:
    pending = state.get("pending") or {}
    tool, args = pending.get("tool", ""), pending.get("args", {})
    session = bsession.get_session(state["run_id"])
    if session is None:
        return {"blocked_reason": "browser session expired", "pending": None}

    tool_def = _registry.get(tool)
    obs = await tool_def.run(session, args) if tool_def else f"ERROR: unknown tool {tool!r}"
    ok = not (obs.startswith("ERROR") or obs.startswith("ASSERTION FAILED"))
    _emit("observation", tool=tool, result=obs)

    entry = {"step": state["step"] + 1, "thought": pending.get("thought", ""), "tool": tool,
             "args": args, "observation": obs, "page_url": session.page.url, "ok": ok}
    return {"pending": None, "step": state["step"] + 1, "scratchpad": state["scratchpad"] + [entry]}


async def approval_node(state: QAState) -> dict:
    pending = state.get("pending") or {}
    tool_def = _registry.get(pending.get("tool"))
    decision = interrupt({
        "tool": pending.get("tool"), "args": pending.get("args"),
        "thought": pending.get("thought"), "step": state["step"], "max_steps": state["max_steps"],
        "page_url": state.get("scratchpad", [{}])[-1].get("page_url"),
        "screenshot_url": state.get("last_screenshot_url"),
        "args_hint": tool_def.args_hint if tool_def else None,
        "schema": tool_def.schema if tool_def else None,
    })
    approved = decision.get("approved") if isinstance(decision, dict) else bool(decision)
    if approved:
        args = (decision.get("edited_args") if isinstance(decision, dict) else None) or pending.get("args", {})
        return {"pending": {**pending, "args": args, "_approved": True}}

    _emit("observation", tool=pending.get("tool"), result="Human REJECTED this submission.")
    entry = {"step": state["step"], "thought": pending.get("thought", ""), "tool": pending.get("tool", ""),
             "args": pending.get("args", {}), "page_url": state.get("scratchpad", [{}])[-1].get("page_url"),
             "observation": "Human REJECTED this form submission. Do not retry it; note it in the report "
                            "if it blocks the scenario, or finish.", "ok": False}
    return {"pending": None, "scratchpad": state["scratchpad"] + [entry]}


async def _audit(scenario: str, action_log: str, findings: str) -> dict:
    s = get_settings()
    try:
        raw = await asyncio.to_thread(
            lambda: chat(verify_messages(scenario, action_log, findings),
                         model=s.text_model, fallback_model=s.vision_fallback,
                         temperature=0.0, max_tokens=800, metadata={"trace_name": "autoqa-verify"}),
        )
        return guards.parse_json(raw)
    except Exception as e:  # pragma: no cover - network dependent
        logger.warning("[verify] auditor call failed: %s", str(e)[:120])
        return {}


async def verify_node(state: QAState) -> dict:
    settings = get_settings()
    scenario = state["scenario"]
    scratchpad = state.get("scratchpad", [])
    session = bsession.get_session(state["run_id"])

    findings = [Finding(**fd) for fd in state.get("findings", [])]
    counter = [len(findings)]

    # 1. Failed assertions in the log → functional findings.
    for s in scratchpad:
        obs = s.get("observation", "")
        if obs.startswith("ASSERTION FAILED"):
            counter[0] += 1
            findings.append(Finding(
                id=f"f{counter[0]}", severity=Severity.MAJOR, category=Category.FUNCTIONAL,
                title=obs[:100], expected="The asserted condition holds",
                actual=obs, page_url=s.get("page_url", state["start_url"]),
                repro_steps=report_mod.repro_steps_from_log(
                    [report_mod.ActionLogEntry(**_log_entry(x)) for x in scratchpad], up_to_step=s.get("step")),
            ))

    # 2. decide's own reported failures.
    fin = state.get("finish") or {}
    for fail in fin.get("failures", []):
        counter[0] += 1
        findings.append(Finding(
            id=f"f{counter[0]}", severity=Severity.MAJOR, category=Category.FUNCTIONAL,
            title=fail.get("title", "Scenario failure")[:100],
            expected=fail.get("expected", ""), actual=fail.get("actual", ""),
            page_url=session.page.url if session else state["start_url"],
        ))

    # 3. blocked reason → a blocked finding.
    if state.get("blocked_reason"):
        counter[0] += 1
        findings.append(Finding(
            id=f"f{counter[0]}", severity=Severity.INFO, category=Category.BLOCKED,
            title="Run blocked", expected="Scenario can be completed",
            actual=state["blocked_reason"],
            page_url=session.page.url if session else state["start_url"]))

    # 4. Auditor LLM — may ADD functional findings; code re-enforces the verdict.
    action_log_str = "\n".join(
        f"{s.get('step')}. {s.get('tool')}({s.get('args')}) -> {s.get('observation', '')[:120]}"
        for s in scratchpad if s.get("tool") and not s["tool"].startswith("_"))
    findings_str = "\n".join(f"- [{f.category.value}] {f.title}" for f in findings) or "(none)"
    if not state.get("forced_finish") or fin.get("verdict") != "blocked":
        audit = await _audit(scenario, action_log_str, findings_str)
        sev_map = {"critical": Severity.CRITICAL, "major": Severity.MAJOR, "minor": Severity.MINOR}
        for af in audit.get("functional_findings", []):
            counter[0] += 1
            findings.append(Finding(
                id=f"f{counter[0]}", severity=sev_map.get(af.get("severity", "major"), Severity.MAJOR),
                category=Category.FUNCTIONAL, title=af.get("title", "")[:100],
                expected=af.get("expected", ""), actual=af.get("actual", ""),
                page_url=session.page.url if session else state["start_url"]))
        summary = audit.get("summary") or fin.get("summary") or "Scenario complete."
    else:
        summary = fin.get("summary") or "Blocked."

    # 5. Merge/dedupe/cap, decide verdict in code, box evidence.
    findings = report_mod.merge_findings(findings, a11y_cap=settings.a11y_max_findings)
    verdict = report_mod.decide_verdict(findings, blocked_reason=state.get("blocked_reason"))
    findings = report_mod.renumber(findings)
    await _attach_evidence(findings, session, state)

    report = report_mod.Report(
        scenario=scenario, start_url=state["start_url"], verdict=verdict, summary=summary,
        findings=findings,
        action_log=[report_mod.ActionLogEntry(**_log_entry(s)) for s in scratchpad
                    if s.get("tool") and not s["tool"].startswith("_")],
        stats=_build_stats(state, findings, session),
    )
    _emit("report", **report.model_dump(mode="json"))
    _progress.pop(state["run_id"], None)
    return {"verdict": verdict}


def _log_entry(s: dict) -> dict:
    return {
        "step": s.get("step", 0), "thought": s.get("thought", ""), "tool": s.get("tool", ""),
        "args": s.get("args", {}), "observation": s.get("observation", ""),
        "page_url": s.get("page_url", ""), "ok": s.get("ok", True),
    }


def _build_stats(state: QAState, findings: list[Finding], session) -> report_mod.Stats:
    actions = [s for s in state.get("scratchpad", []) if s.get("tool") and not s["tool"].startswith("_")]
    by_cat: dict[str, int] = {}
    for f in findings:
        by_cat[f.category.value] = by_cat.get(f.category.value, 0) + 1
    return report_mod.Stats(
        steps=state.get("step", 0),
        actions_ok=sum(1 for s in actions if s.get("ok")),
        actions_error=sum(1 for s in actions if not s.get("ok")),
        pages_visited=len(session.visited_urls) if session else 0,
        findings_by_category=by_cat,
        duration_s=round(time.time() - state.get("started_at", time.time()), 1),
    )


async def _attach_evidence(findings: list[Finding], session, state: QAState) -> None:
    """Box the failing element on the latest screenshot for functional findings
    that name an element; otherwise attach the plain latest screenshot."""
    settings = get_settings()
    shot_url = state.get("last_screenshot_url")
    fin = state.get("finish") or {}
    fail_targets = {f.get("title", ""): (f.get("role"), f.get("name")) for f in fin.get("failures", [])}
    run_dir = settings.runs_dir_path / state["run_id"]

    for f in findings:
        if f.category is not Category.FUNCTIONAL or not shot_url:
            if shot_url and f.category in (Category.CONSOLE, Category.NETWORK, Category.A11Y, Category.BROKEN_LINK):
                f.evidence = Evidence(screenshot_url=shot_url)
            continue
        role, name = fail_targets.get(f.title, (None, None))
        boxed = False
        elem = None
        if session and role and name:
            try:
                async def box_evidence() -> tuple[bytes, dict] | None:
                    loc = session.page.get_by_role(role, name=name).first
                    box = await loc.bounding_box()
                    if not box:
                        return None
                    png = await session.page.screenshot()
                    return png, box

                boxed_result = await pw_run(box_evidence())
                if boxed_result is not None:
                    png, box = boxed_result
                    out = run_dir / f"{f.id}.png"
                    out.write_bytes(annotate.box_element(png, box))
                    shot_url_f = f"/runs/{state['run_id']}/{f.id}.png"
                    f.evidence = Evidence(screenshot_url=shot_url_f, boxed=True,
                                          element=f"role={role} name={name!r}")
                    boxed = True
                    elem = f"role={role} name={name!r}"
            except Exception:  # pragma: no cover
                pass
        if not boxed:
            f.evidence = Evidence(screenshot_url=shot_url, element=elem)


# --------------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------------
def route_after_decide(state: QAState) -> str:
    if state.get("finish") or state.get("forced_finish"):
        return "verify"
    pending = state.get("pending") or {}
    if not pending:
        return "decide"   # a nudge with no action — re-decide
    if needs_approval(pending.get("tool", ""), pending.get("args", {})):
        return "approval"
    return "act"


def route_after_approval(state: QAState) -> str:
    pending = state.get("pending") or {}
    return "act" if pending.get("_approved") else "decide"


# --------------------------------------------------------------------------
# Graph assembly + durable checkpointer
# --------------------------------------------------------------------------
def build_graph(checkpointer: BaseCheckpointSaver):
    g = StateGraph(QAState)
    g.add_node("bootstrap", bootstrap_node)
    g.add_node("observe", observe_node)
    g.add_node("decide", decide_node)
    g.add_node("act", act_node)
    g.add_node("approval", approval_node)
    g.add_node("verify", verify_node)

    g.add_edge(START, "bootstrap")
    g.add_edge("bootstrap", "observe")
    g.add_edge("observe", "decide")
    g.add_conditional_edges("decide", route_after_decide, ["act", "approval", "verify", "decide"])
    g.add_conditional_edges("approval", route_after_approval, ["act", "decide"])
    g.add_edge("act", "observe")
    g.add_edge("verify", END)
    return g.compile(checkpointer=checkpointer)


_graph = None
_agent_conn: aiosqlite.Connection | None = None
_graph_lock = asyncio.Lock()


async def get_graph():
    global _graph, _agent_conn
    async with _graph_lock:
        if _graph is None:
            _agent_conn = await aiosqlite.connect(get_settings().agent_db_path, timeout=10)
            await _agent_conn.execute("PRAGMA journal_mode=WAL")
            await _agent_conn.execute("PRAGMA busy_timeout=10000")
            saver = AsyncSqliteSaver(_agent_conn)
            await saver.setup()
            _graph = build_graph(saver)
    return _graph


async def close_graph() -> None:
    global _graph, _agent_conn
    if _agent_conn is not None:
        await _agent_conn.close()
    _graph = None
    _agent_conn = None
