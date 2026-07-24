"""AutoQA FastAPI app: run a browser QA scenario (SSE trace + streamed
screenshots), approve form submissions, browse/replay run history.

Serves two static mounts:
  * /runs  — per-run screenshots (the SSE `screenshot`/report events carry
             these URLs; replay reads the same files)
  * /demo  — the bundled seeded-bugs mini-site (deterministic eval target)
"""
from __future__ import annotations

import asyncio
import json
import logging
import logging.config
import shutil
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command

from .. import runs_store
from ..agent.graph import close_graph, get_graph
from ..browser import session as bsession
from ..config import get_settings
from ..models import ApprovalRequest, RunDetail, RunRequest, RunSummary
from ..tracing_compat import flush

settings = get_settings()

logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"default": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                               "datefmt": "%H:%M:%S"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "default"}},
    "loggers": {
        "autoqa": {"level": "INFO", "handlers": ["console"], "propagate": False},
        "uvicorn.access": {"level": "WARNING"},
    },
    "root": {"level": "WARNING"},
})
logger = logging.getLogger("autoqa.api")


def _sweep_old_runs() -> None:
    """Keep only the newest RUNS_KEEP run folders on disk."""
    root = settings.runs_dir_path
    if not root.is_dir():
        return
    folders = sorted((p for p in root.iterdir() if p.is_dir()),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in folders[settings.runs_keep:]:
        shutil.rmtree(stale, ignore_errors=True)


from ..db.database import init_db
from ..engines.rca_engine import RCAEngine
from ..engines.self_healing_engine import SelfHealingEngine
from ..engines.visual_regression_engine import VisualRegressionEngine
from ..engines.ux_evaluator import UXEvaluator
from ..engines.patch_generator import PatchGenerator
from ..engines.release_readiness_engine import ReleaseReadinessEngine
from ..engines.coverage_engine import CoverageEngine
from ..engines.knowledge_graph_engine import KnowledgeGraphEngine
from ..engines.report_exporter import ReportExporter

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.runs_dir_path.mkdir(parents=True, exist_ok=True)
    _sweep_old_runs()
    try:
        init_db()                     # initialize relational SQLite schema
        await get_graph()             # open the durable checkpoint DB up front
        await bsession.get_browser()  # launch Chromium once (~1s) not on first run
    except Exception:
        logger.exception("[api] startup warmup failed")
    yield
    await bsession.shutdown_browser()
    await close_graph()


app = FastAPI(title="AutoQA Enterprise AI Platform API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/runs", StaticFiles(directory=str(settings.runs_dir_path)), name="runs")
app.mount("/demo", StaticFiles(directory=str(settings.demo_site_dir), html=True), name="demo")

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
_UNPERSISTED_EVENTS = {"status"}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _record(run_id: str, event: str, data: dict) -> None:
    try:
        await asyncio.to_thread(runs_store.append_event, run_id, event, data)
    except Exception:
        logger.exception("[api] failed to persist event=%s run=%s", event, run_id[:8])


async def _stream_graph(graph_input, run_id: str):
    """Stream agent events; `paused` on an approval interrupt, else `done`.

    The browser session is torn down when the run reaches a terminal state
    (done/error) — but NOT on `paused`, so a human can approve and the same
    live page continues.
    """
    graph = await get_graph()
    config = {"configurable": {"thread_id": run_id}, "recursion_limit": 80}
    t0 = time.monotonic()
    verdict, findings_count = None, 0
    terminal = False
    try:
        async for mode, chunk in graph.astream(graph_input, config, stream_mode=["custom", "updates"]):
            if mode == "custom":
                etype, edata = chunk.get("type", "status"), chunk.get("data", {})
                if etype not in _UNPERSISTED_EVENTS:
                    await _record(run_id, etype, edata)
                if etype == "report":
                    verdict = edata.get("verdict")
                    findings_count = len(edata.get("findings", []))
                yield _sse(etype, edata)
            elif mode == "updates" and isinstance(chunk, dict) and "__interrupt__" in chunk:
                payload = {}
                try:
                    payload = chunk["__interrupt__"][0].value or {}
                except Exception:
                    pass
                logger.info("[api] run=%s paused for approval tool=%s", run_id[:8], payload.get("tool"))
                await _record(run_id, "approval_required", payload)
                yield _sse("approval_required", payload)
                await asyncio.to_thread(runs_store.set_status, run_id, "paused")
                yield _sse("paused", {"run_id": run_id})
                return  # keep the session alive for resume
    except asyncio.CancelledError:
        logger.info("[api] run=%s stopped by client disconnect", run_id[:8])
        await asyncio.to_thread(runs_store.set_status, run_id, "stopped")
        terminal = True
        raise
    except Exception as e:
        msg = str(e)
        low = msg.lower()
        logger.error("[api] run=%s error after %.1fs: %s", run_id[:8], time.monotonic() - t0, msg[:200])
        if any(k in low for k in ("rate limit", "ratelimit", "429", "503", "unavailable", "overloaded")):
            friendly = ("The free Gemini vision tier is momentarily rate-limited. This is transient — "
                        "wait ~1 minute and retry, or space out runs.")
        else:
            friendly = f"The run failed: {msg[:240]}"
        await _record(run_id, "error", {"message": friendly})
        await asyncio.to_thread(runs_store.finish_run, run_id, "error", round(time.monotonic() - t0, 1))
        yield _sse("error", {"message": friendly})
        terminal = True
        return
    finally:
        if terminal:
            await bsession.close_session(run_id)
    elapsed = time.monotonic() - t0
    logger.info("[api] run=%s done in %.1fs verdict=%s", run_id[:8], elapsed, verdict)
    await asyncio.to_thread(runs_store.finish_run, run_id, "done", round(elapsed, 1),
                            verdict=verdict, findings_count=findings_count)
    await bsession.close_session(run_id)
    yield _sse("done", {"run_id": run_id, "verdict": verdict, "elapsed_s": round(elapsed, 1)})
    flush()


@app.post("/run")
async def run(req: RunRequest) -> StreamingResponse:
    run_id = uuid.uuid4().hex
    max_steps = min(req.max_steps or settings.agent_max_steps, settings.agent_max_steps_cap)
    logger.info("[api] /run run=%s url=%r scenario=%r", run_id[:8], req.url[:60], req.scenario[:80])
    await asyncio.to_thread(runs_store.create_run, run_id, req.scenario, req.url)
    graph_input = {"run_id": run_id, "scenario": req.scenario, "start_url": req.url,
                   "step": 0, "max_steps": max_steps}

    async def gen():
        yield _sse("status", {"phase": "started", "run_id": run_id})
        async for frame in _stream_graph(graph_input, run_id):
            yield frame

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)


@app.post("/resume")
async def resume(req: ApprovalRequest) -> StreamingResponse:
    """Resume a paused run after the human approves/rejects a form submission.

    If the browser session expired (e.g. a backend restart killed it — the
    checkpoint survives but the live page doesn't), report it cleanly instead
    of crashing."""
    if bsession.get_session(req.run_id) is None:
        async def expired():
            yield _sse("error", {"message": "This run's browser session expired (likely a backend "
                                            "restart). Start a new run."})
            yield _sse("done", {"run_id": req.run_id, "verdict": None})
        await asyncio.to_thread(runs_store.set_status, req.run_id, "error")
        return StreamingResponse(expired(), media_type="text/event-stream", headers=SSE_HEADERS)

    await asyncio.to_thread(runs_store.set_status, req.run_id, "running")
    cmd = Command(resume={"approved": req.approved, "edited_args": req.edited_args})

    async def gen():
        yield _sse("status", {"phase": "resumed", "run_id": req.run_id})
        async for frame in _stream_graph(cmd, req.run_id):
            yield frame

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)


# History API lives under /history — /runs is the StaticFiles mount for
# screenshots (a `GET /runs` route would be shadowed by that mount).
@app.get("/history", response_model=list[RunSummary])
def list_runs(limit: int = 50) -> list[RunSummary]:
    return [RunSummary(**r) for r in runs_store.list_runs(limit)]


@app.get("/history/{run_id}", response_model=RunDetail)
def get_run(run_id: str) -> RunDetail:
    summary = runs_store.get_run(run_id)
    if summary is None:
        raise HTTPException(404, "Unknown run.")
    return RunDetail(**summary, events=runs_store.get_run_events(run_id))


@app.delete("/history/{run_id}")
def delete_run(run_id: str) -> dict:
    runs_store.delete_run(run_id)
    shutil.rmtree(settings.runs_dir_path / run_id, ignore_errors=True)
    return {"deleted": run_id}


@app.get("/health")
async def health() -> dict:
    browser_ok = False
    try:
        b = await bsession.get_browser()
        browser_ok = b.is_connected()
    except Exception as e:  # pragma: no cover
        return {"status": "ok", "browser_ok": False, "error": str(e)[:200]}
    return {"status": "ok", "browser_ok": browser_ok, "vision_model": settings.vision_model}


@app.get("/")
def root() -> dict:
    return {"name": "AutoQA Enterprise AI Quality Engineering Platform", "docs": "/docs", "health": "/health"}


# --- ENTERPRISE AI QUALITY PLATFORM API ENDPOINTS ---

@app.post("/api/v1/rca/analyze")
def analyze_root_cause(payload: dict) -> dict:
    rca = RCAEngine.analyze_finding(
        finding_type=payload.get("type", "functional"),
        title=payload.get("title", "Execution Error"),
        description=payload.get("description", "Failure observed during flow"),
        console_logs=payload.get("console_logs", []),
        network_logs=payload.get("network_logs", []),
        aria_snapshot=payload.get("aria_snapshot"),
        url=payload.get("url"),
    )
    patch = PatchGenerator.generate_patch_for_finding(
        title=rca.title,
        finding_type=payload.get("type", "functional"),
        root_cause=rca.root_cause_explanation,
        suggested_fix=rca.suggested_patch,
    )
    return {"rca": rca.model_dump(), "patch": patch.model_dump()}


@app.post("/api/v1/self-healing/heal")
def self_healing_locator(payload: dict) -> dict:
    candidate = SelfHealingEngine.attempt_recovery(
        failed_selector=payload.get("failed_selector", "button.submit"),
        target_role=payload.get("target_role"),
        target_name=payload.get("target_name"),
        aria_snapshot_text=payload.get("aria_snapshot_text"),
    )
    return candidate.model_dump()


@app.post("/api/v1/coverage/analyze")
def prd_coverage_analysis(payload: dict) -> dict:
    prd_text = payload.get("prd_text", "Feature: User Authentication & Cart Checkout Flow.")
    mappings = CoverageEngine.analyze_prd_text(prd_text)
    return {"mappings": [m.model_dump() for m in mappings]}


@app.get("/api/v1/knowledge-graph")
def get_knowledge_graph(project_id: str = "default") -> dict:
    graph = KnowledgeGraphEngine.get_project_graph(project_id)
    return graph.model_dump()


@app.get("/api/v1/release-readiness")
def get_release_readiness(
    project_id: str = "default",
    build_version: str = "v2.4.1",
    verdict: str = "pass",
    findings_count: int = 0,
) -> dict:
    report = ReleaseReadinessEngine.calculate_readiness(
        project_id=project_id,
        build_version=build_version,
        verdict=verdict,
        findings_count=findings_count,
    )
    return report.model_dump()


@app.post("/api/v1/reports/export")
def export_report(payload: dict) -> dict:
    run_id = payload.get("run_id", "latest")
    url = payload.get("url", "http://localhost:5173")
    scenario = payload.get("scenario", "Automated QA Verification")
    verdict = payload.get("verdict", "pass")
    score = payload.get("release_score", 95.0)
    findings = payload.get("findings", [])
    rca_list = payload.get("rca_list", [])

    markdown_doc = ReportExporter.export_report_markdown(
        run_id=run_id,
        url=url,
        scenario=scenario,
        verdict=verdict,
        release_score=score,
        findings=findings,
        rca_results=rca_list,
    )
    return {"run_id": run_id, "markdown": markdown_doc, "json": payload}

