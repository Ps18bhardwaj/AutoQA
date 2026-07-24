"""Phase-3 CLI: drive one QA scenario end to end without the web UI.

Runs the real agent graph (REAL Gemini vision calls — needs GEMINI_API_KEY),
auto-approves any form-submission gate, prints each event, and dumps the final
report JSON. Serves the bundled demo site on a background thread so `/demo`
URLs work offline.

    python scripts/run_scenario.py --url https://www.saucedemo.com \
        --scenario "Log in as standard_user / secret_sauce and confirm the inventory page loads." \
        --max-steps 12
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from langgraph.types import Command  # noqa: E402

from app.agent.graph import build_graph, close_graph  # noqa: E402
from app.browser import session as bsession  # noqa: E402
from app.config import get_settings  # noqa: E402

_DEMO_DIR = get_settings().demo_site_dir


class _DemoHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.startswith("/demo/api/"):
            self.send_response(404); self.end_headers(); return
        rel = path[len("/demo/"):] if path.startswith("/demo/") else path.lstrip("/")
        rel = rel or "index.html"
        target = (_DEMO_DIR / rel).resolve()
        if not str(target).startswith(str(_DEMO_DIR)) or not target.is_file():
            self.send_response(404); self.end_headers(); return
        ctype = "text/html" if target.suffix == ".html" else "image/png"
        body = target.read_bytes()
        self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)


def _serve_demo() -> int:
    httpd = ThreadingHTTPServer(("127.0.0.1", 8003), _DemoHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return 8003


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--max-steps", type=int, default=12)
    ap.add_argument("--auto-approve", action="store_true", default=True)
    args = ap.parse_args()

    if "/demo" in args.url or "localhost:8003" in args.url or "127.0.0.1:8003" in args.url:
        _serve_demo()
        print("[demo site served on :8003]")

    from langgraph.checkpoint.memory import MemorySaver
    graph = build_graph(MemorySaver())
    run_id = uuid.uuid4().hex[:12]
    config = {"configurable": {"thread_id": run_id}, "recursion_limit": 80}
    initial = {"run_id": run_id, "scenario": args.scenario, "start_url": args.url,
               "step": 0, "max_steps": args.max_steps}

    report = None
    stream = graph.astream(initial, config, stream_mode=["custom", "updates"])
    try:
        while True:
            async for mode, chunk in stream:
                if mode == "custom":
                    etype, data = chunk["type"], chunk["data"]
                    if etype == "report":
                        report = data
                    elif etype == "screenshot":
                        print(f"  [screenshot] step {data['step']} -> {data['url']} ({data.get('title','')[:40]})")
                    elif etype == "thought":
                        print(f"  [thought] {data['text'][:120]}")
                    elif etype == "action":
                        print(f"  [action] {data['tool']}({json.dumps(data['args'])})")
                    elif etype == "observation":
                        print(f"  [obs] {data['result'][:120]}")
                    elif etype == "finding":
                        print(f"  [finding] {data['severity']}/{data['category']}: {data['title']}")
                elif mode == "updates" and "__interrupt__" in chunk:
                    payload = chunk["__interrupt__"][0].value or {}
                    print(f"  [APPROVAL NEEDED] {payload.get('tool')}({payload.get('args')}) "
                          f"-> auto-approving")
                    stream = graph.astream(Command(resume={"approved": True}), config,
                                           stream_mode=["custom", "updates"])
                    break
            else:
                break
    finally:
        await bsession.close_session(run_id)
        await bsession.shutdown_browser()
        await close_graph()

    print("\n" + "=" * 60)
    if report:
        print(f"VERDICT: {report['verdict'].upper()}")
        print(f"SUMMARY: {report['summary']}")
        print(f"FINDINGS: {len(report['findings'])}")
        for f in report["findings"]:
            print(f"  - [{f['severity']}/{f['category']}] {f['title']}")
        print(f"STATS: {json.dumps(report['stats'])}")
    else:
        print("No report produced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
