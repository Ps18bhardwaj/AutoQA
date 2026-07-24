"""AutoQA eval harness.

Drives the REAL agent graph over each scenario (real Chromium, real Gemini
vision — needs GEMINI_API_KEY), auto-approving any form-submission gate (it
plays the human), and scores:

  * verdict accuracy   — report.verdict == expected_verdict
  * findings precision/recall — predicted vs expected {category, keyword},
    greedy 1:1 match (category equal AND keyword in title+actual). info-severity
    a11y findings are excluded from precision (advisory noise).
  * action-success rate — non-ERROR / non-failed-target actions ÷ total actions
    (a deliberate ASSERTION FAILED on a buggy page is NOT counted as a failure —
    the assertion worked; the harness knows from ground truth).

Serves the bundled /demo site on :8003 so the local scenarios resolve.
Writes eval/results.md.

    python eval/run_eval.py [--limit N] [--only demo] [--out eval/results.md]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.types import Command  # noqa: E402

from app.agent.graph import build_graph  # noqa: E402
from app.browser import session as bsession  # noqa: E402
from app.config import get_settings  # noqa: E402

_DEMO_DIR = get_settings().demo_site_dir


class _DemoHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _serve(self, body: bool):
        path = self.path.split("?")[0]
        if path.startswith("/demo/api/"):
            self.send_response(404); self.end_headers(); return
        rel = path[len("/demo/"):] if path.startswith("/demo/") else path.lstrip("/")
        rel = rel or "index.html"
        target = (_DEMO_DIR / rel).resolve()
        if not str(target).startswith(str(_DEMO_DIR)) or not target.is_file():
            self.send_response(404); self.end_headers(); return
        data = target.read_bytes()
        ctype = "text/html" if target.suffix == ".html" else "image/png"
        self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data))); self.end_headers()
        if body:
            self.wfile.write(data)

    def do_GET(self):
        self._serve(True)

    def do_HEAD(self):
        self._serve(False)


def _serve_demo():
    httpd = ThreadingHTTPServer(("127.0.0.1", 8003), _DemoHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()


async def _run_one(graph, scenario: dict) -> dict:
    run_id = f"eval-{scenario['id']}"
    config = {"configurable": {"thread_id": run_id}, "recursion_limit": 80}
    initial = {"run_id": run_id, "scenario": scenario["scenario"], "start_url": scenario["url"],
               "step": 0, "max_steps": scenario.get("max_steps", 12)}
    report = None
    approvals = 0
    stream = graph.astream(initial, config, stream_mode=["custom", "updates"])
    try:
        while True:
            async for mode, chunk in stream:
                if mode == "custom" and chunk.get("type") == "report":
                    report = chunk["data"]
                elif mode == "updates" and isinstance(chunk, dict) and "__interrupt__" in chunk:
                    approvals += 1
                    stream = graph.astream(Command(resume={"approved": True}), config,
                                           stream_mode=["custom", "updates"])
                    break
            else:
                break
    finally:
        await bsession.close_session(run_id)
    return {"report": report, "approvals": approvals}


def _match_findings(expected: list[dict], predicted: list[dict]) -> int:
    """Greedy 1:1: expected matches a predicted finding iff same category AND
    keyword appears in (title + actual). Returns the true-positive count."""
    remaining = list(predicted)
    tp = 0
    for exp in expected:
        for i, pred in enumerate(remaining):
            hay = f"{pred.get('title', '')} {pred.get('actual', '')}".lower()
            if pred.get("category") == exp["category"] and exp["keyword"].lower() in hay:
                tp += 1
                remaining.pop(i)
                break
    return tp


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="", help="substring filter on scenario id")
    ap.add_argument("--out", default=str(Path(__file__).parent / "results.md"))
    args = ap.parse_args()

    data = json.loads((Path(__file__).parent / "dataset.json").read_text(encoding="utf-8"))
    scenarios = data["scenarios"]
    if args.only:
        scenarios = [s for s in scenarios if args.only in s["id"]]
    if args.limit:
        scenarios = scenarios[:args.limit]

    _serve_demo()
    graph = build_graph(MemorySaver())

    rows = []
    tp_total = pred_total = exp_total = 0
    verdict_ok = 0
    act_ok = act_total = 0

    for i, sc in enumerate(scenarios):
        print(f"[{i+1}/{len(scenarios)}] {sc['id']} …", flush=True)
        t0 = time.perf_counter()
        try:
            out = await _run_one(graph, sc)
        except Exception as e:
            print(f"    ERROR: {str(e)[:160]}")
            rows.append({"id": sc["id"], "verdict": "ERROR", "expected": sc["expected_verdict"],
                         "vmatch": False, "tp": 0, "exp": len(sc.get("expected_findings", [])),
                         "pred": 0, "dt": time.perf_counter() - t0})
            continue
        rep = out["report"] or {}
        verdict = rep.get("verdict", "none")
        vmatch = verdict == sc["expected_verdict"]
        verdict_ok += int(vmatch)

        # findings precision/recall (exclude info-severity a11y from precision)
        predicted = [f for f in rep.get("findings", [])
                     if not (f.get("category") == "a11y" and f.get("severity") == "info")]
        expected = sc.get("expected_findings", [])
        tp = _match_findings(expected, predicted)
        tp_total += tp
        pred_total += len(predicted)
        exp_total += len(expected)

        # action-success from the action log
        for a in rep.get("action_log", []):
            if a.get("tool", "").startswith("assert"):
                continue  # assertions are checks, not navigation actions
            act_total += 1
            act_ok += int(a.get("ok", True))

        rows.append({"id": sc["id"], "verdict": verdict, "expected": sc["expected_verdict"],
                     "vmatch": vmatch, "tp": tp, "exp": len(expected), "pred": len(predicted),
                     "dt": time.perf_counter() - t0})
        print(f"    verdict={verdict} (expected {sc['expected_verdict']}) "
              f"findings tp={tp}/{len(expected)} pred={len(predicted)} ({time.perf_counter()-t0:.0f}s)")

    await bsession.shutdown_browser()

    precision = tp_total / pred_total if pred_total else 1.0
    recall = tp_total / exp_total if exp_total else 1.0
    verdict_acc = verdict_ok / len(rows) if rows else 0.0
    action_success = act_ok / act_total if act_total else 1.0

    lines = [
        "# AutoQA eval results",
        "",
        f"{len(rows)} scenarios (saucedemo + the-internet + local seeded-bugs demo), "
        f"real Chromium + `{get_settings().vision_model}` vision. Generated on your machine "
        "from your free keys — not pre-baked.",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Verdict accuracy | **{verdict_acc:.0%}** ({verdict_ok}/{len(rows)}) |",
        f"| Findings precision | **{precision:.0%}** ({tp_total}/{pred_total}) |",
        f"| Findings recall | **{recall:.0%}** ({tp_total}/{exp_total}) |",
        f"| Action-success rate | **{action_success:.0%}** ({act_ok}/{act_total}) |",
        "",
        "_Precision/recall are over scenarios that declare `expected_findings` "
        "(incl. the clean-page control with zero); info-severity a11y findings are "
        "excluded from precision as advisory noise. Action-success excludes assertions "
        "(they're checks, not actions — a deliberate ASSERTION FAILED on a buggy page is "
        "the tool working correctly)._",
        "",
        "| Scenario | Verdict | Expected | ✓ | Findings tp/exp | Predicted | Time |",
        "|---|---|---|:-:|:-:|:-:|--:|",
    ]
    for r in rows:
        lines.append(f"| {r['id']} | {r['verdict']} | {r['expected']} | "
                     f"{'✅' if r['vmatch'] else '❌'} | {r['tp']}/{r['exp']} | {r['pred']} | {r['dt']:.0f}s |")

    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {args.out}")
    print(f"verdict={verdict_acc:.0%} precision={precision:.0%} recall={recall:.0%} action={action_success:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
