# Project 4 — AutoQA: Autonomous Browser QA Agent

> A teaching guide you can rebuild the project from. Every code snippet is from the
> real build; model IDs and versions are what was actually used (verified 2026-07).
> The GenAI stack moves weekly — re-check free model IDs on Google AI Studio if you're
> following this much later.

---

## 1. What we built & why it matters

**AutoQA is a browser QA agent you point at any public URL.** You type a test scenario in
plain English ("log in as standard_user, add the cheapest item to the cart, the badge must
show 1"), watch it **drive a real Chromium browser**, and get back a **structured bug report**
with severity, repro steps, and red-boxed screenshot evidence — all on **free-tier models**
(`gemini-3.5-flash` for vision decisions, Playwright for the browser, axe-core for accessibility).

**Why it matters for hiring:** computer-use / browser agents are 2026's fastest-growing agent
category, and the interesting engineering isn't "call a vision model in a loop." It's the
**vision-grounded observe→decide→act→verify loop**, the **QA-specific observation stack**
(ARIA snapshot + screenshot + console/network/axe capture), and **agent safety** — domain
allowlist, read-only-by-default tools, a human-approval gate before form submission, and a
credential guard that refuses real passwords or payment data. AutoQA builds the loop itself
(no `browser-use` wrapper) so every rail is explicit and inspectable.

**Resume bullet:**
> Built an autonomous browser QA agent: a hand-built LangGraph observe→decide→act→verify loop
> where a vision LLM (`gemini-3.5-flash`) drives Playwright via a typed, whitelisted action
> set grounded in the page's ARIA snapshot; per-page axe-core / console / network / broken-link
> checks; a Pydantic bug report with severity, repro steps, and red-boxed screenshot evidence;
> safety rails (domain allowlist, read-only default, human-approval gate on form submission,
> credential guard); durable SQLite run history with a live streamed "agent viewport" UI; and a
> 19-scenario eval scoring bug-detection precision/recall, verdict accuracy, and action-success
> — all free-tier.

---

## 2. Prerequisites

**Accounts / keys (all free):**
- **Google AI Studio** — [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey).
  AutoQA's **decide step needs vision** → Gemini only (Groq has no vision models on the free
  tier). Set `GEMINI_API_KEY` and `GOOGLE_API_KEY` (LiteLLM reads both names).
- **Groq** (optional) — [console.groq.com/keys](https://console.groq.com/keys). Only used by
  the vendored router for text-only fallbacks; the decide chain is Gemini-only.
- **Langfuse** (optional) — free cloud tier for tracing; leave keys blank to disable.

**Set up your keys:**
```bash
cd 4-autoqa
cp .env.example .env    # then edit .env and paste GEMINI_API_KEY
```

**Tools:** Python 3.11+, Node 20+, `uv`. Playwright Chromium (~150 MB one-time download).
No Docker required locally — SQLite is a file; the demo site is bundled.

**Assumed knowledge:** async Python, React + TypeScript, the *idea* of an LLM agent loop, and
basic browser automation concepts. Playwright and LangGraph are explained as we build.

**Windows note:** run `playwright install chromium` once. If you see `NotImplementedError` on
startup, see §8 — we solved it with a dedicated Playwright event-loop thread (`_pw_loop.py`).

---

## 3. Architecture

```
┌────────────────── React + Vite frontend ──────────────────┐        ┌──────────────────── FastAPI backend ─────────────────────┐
│  ScenarioForm (URL + scenario + sample chips)              │        │  LangGraph state machine (per-run, durably checkpointed) │
│  AgentViewport ── live streamed screenshots (SSE) ─────────│  POST  │                                                          │
│  AgentTrace ── thoughts / actions / observations / findings│  /run  │   START → bootstrap → observe → decide ─┬─ act ──┐       │
│  ApprovalModal ── form-submission gate (+ screenshot)      │◀──SSE──│                        ▲               │        │       │
│  ReportView ── verdict + findings + boxed evidence + log   │  /resume│                       │   (submit?)   ├─ approval ─interrupt
│  RunsMenu ── browsable/replayable history                  │────────▶│                       └───(act)───────┘        │(pause)  │
└────────────────────────────────────────────────────────────┘        │                        └─(finish|blocked|limit|loop)─▶ verify → END
                          ▲   /runs/<id>/step_N.png  (screenshots)      │                                                          │
                          └───────────────────────────────────────────│  browser/  session + _pw_loop (Playwright thread)      │
                                                                       │            tools   (navigate/click/type/submit/assert…)   │
                                                                       │            checks  (axe + console + network + links)      │
                                                                       │            annotate (Pillow red-box on evidence)          │
                                                                       │  agent/    graph · guards · prompts                        │
                                                                       │  report.py (Finding/Report + code-decided verdict)         │
                                                                       │  safety.py (allowlist · credential guard · block detect)   │
                                                                       │  shared/llm.py  Gemini vision decide + Flash-Lite fallback   │
                                                                       └──────────────────────────────────────────────────────────┘
```

### The agent loop (control flow)
1. **bootstrap** — create an isolated Playwright `BrowserContext`+`Page`, navigate to the start URL.
2. **observe** — ARIA snapshot + screenshot; on each *new* URL run axe-core, broken-image sweep,
   capped dead-link check; every step drain console/network buffers into findings; detect CAPTCHAs.
3. **decide** — one **vision** LLM call: scenario + history + ARIA text + screenshot JPEG. Returns
   strict JSON — either one action or a finish verdict. Loop/no-progress guards short-circuit
   runaway runs; a premature-finish guard blocks "pass" with zero actions.
4. **act** — dispatch one typed tool; the observation string **never raises** (bad selector →
   `"ERROR: …"` the agent reads and adapts to).
5. **approval** — if the action is a **form submission** (or Enter-in-form), the graph
   `interrupt()`s; the UI shows an approval dialog; `/resume` continues via `Command(resume=…)`.
6. **verify** — assemble the report. Failed assertions + decide-node failures + an auditor LLM pass
   feed findings; **`decide_verdict()` in code** sets the final pass/fail/blocked — the model can
   *add* findings but cannot launder a functional failure into a pass.

### Element targeting: ARIA `{role, name}`, not CSS
The decide model picks elements from the **accessible role + name in the snapshot** →
`page.get_by_role(role, name=name)` with a `get_by_text` fallback. This survives dynamic
class/id churn, can't produce selector-syntax errors, and keeps the screenshot for visual
context rather than pixel-coordinate clicking.

---

## 4. Step-by-step build

The build order de-risks the scary parts first (does Playwright even work on this machine?),
then walks outward: browser stack → safety → tools → graph → API → frontend → eval.

### 4.0 Go/no-go: prove Playwright works — `scripts/smoke_browser.py`

Before writing any agent code, launch headless Chromium and exercise every primitive the agent
will rely on: ARIA snapshot, screenshot bytes, axe-core injection, console/network listeners.
If this script fails, fix the environment before building the loop.

```bash
cd backend
./.venv/Scripts/playwright.exe install chromium   # one-time
./.venv/Scripts/python.exe scripts/smoke_browser.py
```

### 4.1 The shared LLM router — `backend/shared/llm.py` (vendored)

Every project in this portfolio imports one `chat()` function. AutoQA's **decide step is
vision-only** — configured via `.env`:

```
VISION_MODEL=gemini/gemini-3.5-flash          # ~15 RPM / ~1,500 RPD free
VISION_FALLBACK=gemini/gemini-3.1-flash-lite  # separate quota, also vision
TEXT_MODEL=gemini/gemini-3.5-flash            # verify-node auditor (text-only)
```

The router retries transient errors with exponential backoff and falls back to Flash-Lite on
rate limits. Langfuse tracing is wired in via LiteLLM callbacks. This file is **vendored into
the project** (not imported from a repo root) so the zip is self-contained.

### 4.2 Windows-safe Playwright — `backend/app/browser/_pw_loop.py`

**The problem:** on Windows, uvicorn with `--reload` uses `SelectorEventLoop`, which cannot run
`asyncio.create_subprocess_exec` — Playwright needs that to spawn its driver subprocess.

**The fix:** all Playwright coroutines run on a **dedicated background thread** with
`ProactorEventLoop`. FastAPI/LangGraph stay on uvicorn's loop; `pw_run(coro)` marshals work
across threads with `asyncio.run_coroutine_threadsafe`:

```python
async def run(coro: Awaitable[T]) -> T:
    pw_loop = _ensure_started()
    caller = asyncio.get_running_loop()
    if pw_loop is caller:
        return await coro
    fut = asyncio.run_coroutine_threadsafe(coro, pw_loop)
    return await asyncio.wrap_future(fut)
```

Every browser touchpoint goes through this: `session.py`, `graph.py` (observe + screenshots),
`tools.py` (`_on_pw_loop` wrapper on each tool). An import-time uvicorn patch **cannot** fix
this — uvicorn creates its event loop *before* loading the app.

### 4.3 Browser lifecycle — `backend/app/browser/session.py`

One Chromium for the process (launched in the FastAPI lifespan); one `BrowserContext`+`Page`
**per run** for cookie isolation. LangGraph state holds only the `run_id` — Playwright objects
aren't checkpoint-serializable — so every graph node does `get_session(run_id)`.

Console/network listeners attach once at session creation and accumulate into run-scoped buffers;
`drain_new()` hands back only what's NEW since the last observe step, so findings are never
double-counted. A route guard aborts off-allowlist **navigation** requests (subresources from
CDNs still pass so pages render).

```python
async def get_browser() -> Browser:
    async def _launch() -> Browser:
        global _pw, _browser
        if _pw is None:
            _pw = await async_playwright().start()
        _browser = await _pw.chromium.launch(headless=settings.headless)
        return _browser
    return await pw_run(_launch())
```

### 4.4 The whitelisted action set — `backend/app/browser/tools.py`

AutoQA's entire action surface is ten typed `Tool`s. Every `run(session, args) -> str` **never
raises** — failures come back as `"ERROR: …"` or `"ASSERTION FAILED: …"` observation strings.

```python
def _on_pw_loop(fn):
    async def wrapped(session, args):
        async def work():
            return await fn(session, args)
        return await pw_run(work())
    return wrapped
```

Key safety baked into the tools (not bolted on afterward):
- **`navigate`** — allowlist-enforced (`safety.is_allowed`)
- **`click`** — refuses form-submit controls (points the agent at the approval-gated `submit`)
- **`type_text`** — credential guard (never types card/SSN-shaped values; password fields only
  on known test hosts or with known test credentials)
- **`submit`** — the ONLY `write=True` tool → human approval before it runs

Element resolution is role/name grounded in the ARIA snapshot the LLM saw:

```python
loc = page.get_by_role(role, name=name, exact=False).first
await loc.wait_for(state="visible", timeout=settings.action_timeout_ms)
```

### 4.5 Safety rails — `backend/app/safety.py`

Pure functions (no Playwright, no LLM) so every branch is keyless-testable. The rails run
**inside** the tools and return `"ERROR: …"` strings the agent can read.

**Domain allowlist** — registrable-domain heuristic (last two labels; no `tldextract` dep):

```python
def is_allowed(url: str, allowlist: set[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in allowlist or registrable_suffix(host) in allowlist
```

**Credential guard** — card/SSN patterns are **always** refused; password-like fields only
accept values on known test hosts (`saucedemo.com`, etc.) or in the configured test-credential
list.

**Block detection** — CAPTCHA/auth-wall heuristics from page title + snapshot text + HTTP status.

### 4.6 Observation → findings — `backend/app/browser/checks.py`

Pure converters turn console/network buffer dicts into `Finding` models. Async sweeps:
- **`run_axe(page)`** — inject vendored `axe.min.js`, return violations (never raises)
- **`broken_image_findings`** — `naturalWidth === 0` on completed images
- **`dead_link_findings`** — HEAD same-allowlist anchors, **GET-confirm** any HEAD failure
  (SPAs often 404 on HEAD for routes GET serves fine)
- Third-party console/network noise from a *different registrable domain* than the page is
  dropped — telemetry 401s on saucedemo aren't the site-under-test's bug.

### 4.7 The agent graph — `backend/app/agent/graph.py`

A LangGraph `StateGraph` with durable SQLite checkpointing (`AsyncSqliteSaver`). Custom events
via `get_stream_writer()` feed the SSE trace in the UI.

**`decide_node`** — pre-LLM guards before spending a vision call:

```python
if state.get("blocked_reason"):
    return {"finish": {"verdict": "blocked", ...}, "forced_finish": True}
if step >= max_steps:
    return {"finish": {"verdict": "fail", ...}, "forced_finish": True}
if guards.detect_no_progress(_progress.get(state["run_id"], [])):
    return {"finish": {"verdict": "fail", ...}, "forced_finish": True}
```

Then one vision call, JSON parse with one corrective retry, premature-finish guard, loop
detection (same tool+args twice → force finish).

**`approval_node`** — LangGraph `interrupt()` carries tool/args/thought/screenshot to the UI:

```python
decision = interrupt({
    "tool": pending.get("tool"), "args": pending.get("args"),
    "screenshot_url": state.get("last_screenshot_url"), ...
})
```

**`verify_node`** — merge findings, run a text-only auditor LLM, then **`decide_verdict()` in
code** — not the model's claim.

**SSE from the Playwright thread:** observe collects stream events in a list inside `pw_work()`,
then replays them via `_emit()` on the main loop after `pw_run()` returns — LangGraph's stream
writer is not safe to call from the browser thread.

### 4.8 The verdict rule — `backend/app/report.py`

This separation is what makes eval precision/recall trustworthy:

```python
def decide_verdict(findings: list[Finding], *, blocked_reason: str | None) -> str:
    if blocked_reason:
        return "blocked"
    if any(f.category is Category.FUNCTIONAL for f in findings):
        return "fail"
    return "pass"
```

`merge_findings()` dedupes by `(category, title, page_url)` and caps a11y findings at the top
10 by severity — axe can emit dozens of near-identical advisory hits.

Evidence screenshots are written to `runs/<id>/step_N.png` and served by `StaticFiles`; the SSE
`screenshot` event carries the URL, not base64-in-SQLite.

### 4.9 The API + SSE streaming — `backend/app/api/main.py`

`POST /run` starts a run and streams the trace as Server-Sent Events. `POST /resume` continues
after human approval. The graph streams with `stream_mode=["custom", "updates"]`:

```python
async for mode, chunk in graph.astream(graph_input, config, stream_mode=["custom", "updates"]):
    if mode == "custom":
        yield _sse(etype, edata)
    elif mode == "updates" and "__interrupt__" in chunk:
        yield _sse("approval_required", payload)
        yield _sse("paused", {"run_id": run_id})
        return  # keep browser session alive for resume
```

On terminal states the browser session is torn down; on `paused` it is **not** — the human can
approve and the same live page continues. A backend restart kills the live browser of a paused
run (checkpoint survives; `/resume` returns "session expired").

Run history persists every event to SQLite (`runs_store.py`) for replay from the **Runs** menu.

### 4.10 The frontend — `frontend/src/`

React 19 + Vite 8 + Tailwind v4 + shadcn/ui. `lib/api.ts` is a typed client with a hand-rolled
**SSE-over-POST** reader (native `EventSource` can't POST a body):

```typescript
async function readSSE(path: string, body: unknown, handlers: StreamHandlers, signal?: AbortSignal) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  // ... parse event: / data: frames incrementally
}
```

`AgentConsole.tsx` wires SSE events → `TraceItem`s via `lib/trace.ts`. `AgentViewport.tsx` renders
live screenshots from SSE `screenshot` events (`<img src={screenshotSrc(url)}>`). `ApprovalModal.tsx`
shows the pending action + screenshot before form submission. `ReportView.tsx` renders the final
verdict, findings with boxed evidence, and the action log.

In dev, Vite proxies `/api` and `/runs` to `:8003` (`vite.config.ts`). In prod set `VITE_API_BASE`
and `VITE_API_ORIGIN` so screenshots load cross-origin from the backend.

### 4.11 The seeded-bugs demo site — `backend/app/demo_site/`

A deterministic eval target served at `/demo` by the backend itself. Ground truth: a functional
"total doesn't update" bug, a broken image, a console error, a failed request, an a11y violation,
plus a clean-page control. The eval harness can score precision/recall exactly against these.

### 4.12 Eval harness — `backend/eval/run_eval.py`

19 scenarios across `/demo`, saucedemo.com, and the-internet.herokuapp.com. The harness drives
the **real graph**, auto-approves the form-submission gate (it plays the human), and scores:
- **Verdict accuracy** — predicted vs expected pass/fail/blocked
- **Findings precision/recall** — category + keyword match against `expected_findings`
- **Action-success rate** — tools that didn't return `ERROR:` (assertions excluded — a deliberate
  `ASSERTION FAILED` on a buggy page is the tool working correctly)

```bash
cd backend
python eval/run_eval.py --only demo     # deterministic subset → eval/results.md
python eval/run_eval.py                 # full 19-scenario suite (slow on free tier)
```

---

## 5. The hard parts & how we solved them

| Problem | Solution |
|---------|----------|
| **Windows + uvicorn `--reload` + Playwright** | Dedicated `_pw_loop` thread with `ProactorEventLoop`; all Playwright coroutines marshaled via `pw_run()` |
| **Playwright objects aren't checkpoint-serializable** | LangGraph state holds only `run_id`; live page in a session registry keyed by that id |
| **Model declares pass over a failed assertion** | Final verdict from `decide_verdict()` in code; auditor LLM can only *add* findings |
| **Auditor laundering a11y noise into functional failures** | Tightened verify prompt to only report scenario-requirement failures (caught a real eval bug) |
| **Dynamic CSS selectors break on SPAs** | ARIA role/name targeting from the snapshot the model was shown |
| **Third-party telemetry pollutes findings** | Drop console/network events from a different registrable domain than the page |
| **Dead-link false positives** | HEAD failures re-checked with GET before reporting |
| **SSE events from browser thread** | Collect in `pw_work()`, emit on main loop after `pw_run()` returns |
| **Free-tier vision rate limits** | Router retries + Flash-Lite fallback; friendly SSE error message on 429 |
| **Form submission safety** | Only `submit` is `write=True`; `click` refuses submit controls; Enter-in-form dynamically gated |

---

## 6. Evaluation & results

Committed numbers are the **deterministic `/demo` subset** (4 scenarios with exact ground truth),
run against real Chromium + `gemini/gemini-3.5-flash`:

| Metric | Result |
|--------|-------:|
| Verdict accuracy | **100%** (4/4) |
| Findings recall | **100%** (5/5) |
| Findings precision | **36%** (5/14) |
| Action-success rate | **100%** |

**Reading the numbers honestly:**
- **Recall 100%** — every planted bug caught (functional total bug, broken image, console error,
  failed request, contrast a11y violation).
- **Verdict 100%** — functional bug correctly fails; clean page and checkout-with-approval correctly pass.
- **Precision 36%** is dragged by demo-03: real a11y issues beyond the planted contrast bug
  (missing landmark, heading order) are legitimately reported but aren't in the minimal ground-truth
  set. The clean-page control and checkout flow both produced **zero** findings.

Full per-scenario breakdown in [`backend/eval/results.md`](backend/eval/results.md).

### Tests (keyless + browser)
```bash
cd backend
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt
python -m pytest -q                 # 46 keyless: report/verdict, safety, guards, API CRUD
python -m pytest -q -m browser      # 11 with real Chromium vs /demo, incl. full graph w/ stubbed LLM
```

---

## 7. Deployment

### Local
```bash
# Backend
cd 4-autoqa/backend
uv venv .venv && uv pip install --python .venv/Scripts/python.exe -r requirements.txt
./.venv/Scripts/playwright.exe install chromium
./.venv/Scripts/python.exe scripts/smoke_browser.py
./.venv/Scripts/uvicorn app.api.main:app --reload --port 8003

# Frontend (new terminal)
cd ../frontend && npm install && npm run dev   # http://localhost:5173
```

### Production (free tier)
| Piece | Target | Notes |
|-------|--------|-------|
| **Backend** | **HF Spaces (Docker)** | `backend/Dockerfile` — Microsoft's Playwright Python image (Chromium preinstalled). **Not Render 512MB** — Chromium needs ≥1GB RAM. Mount volume for `autoqa.db` + `runs/` if filesystem doesn't persist. |
| **Frontend** | **Vercel** | Set `VITE_API_BASE` + `VITE_API_ORIGIN` to backend origin; add Vercel origin to `CORS_ORIGINS`. |
| **Tracing** | Langfuse cloud | Set `LANGFUSE_*` env vars. |

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.61.0-noble
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY shared ./shared
EXPOSE 8003
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8003"]
```

Build: `docker build -t autoqa-api .` from `backend/`. Runtime needs `GEMINI_API_KEY`.

---

## 8. Common errors & fixes

- **`NotImplementedError` on startup (Windows)** — uvicorn `--reload` uses `SelectorEventLoop`,
  which can't spawn Playwright's driver. Fixed in `_pw_loop.py` (§4.2). Restart the server after
  pulling; you should see `[browser] chromium launched` in the logs.
- **`Executable doesn't exist` / Playwright browser missing** — run
  `./.venv/Scripts/playwright.exe install chromium` once (~150 MB).
- **`ModuleNotFoundError`** when running scripts — you used system `python` instead of the venv:
  `./.venv/Scripts/python.exe scripts/...`.
- **Gemini 429 / rate-limited during a run** — transient on the free tier (~15 RPM for Flash).
  Wait ~1 minute and retry; the router falls back to Flash-Lite. Space out eval sweeps.
- **`session expired` on `/resume`** — the backend restarted while a run was paused. The checkpoint
  survived but the live browser didn't. Start a new run.
- **Screenshots blank in prod** — set `VITE_API_ORIGIN` to the backend URL so `<img>` can load
  `/runs/...` cross-origin.
- **Agent navigates off-site** — allowlist blocked it (safe failure). Add hosts to `ALLOWLIST_EXTRA`
  in `.env` only if you intend to test cross-domain flows.
- **Mic / voice errors** — wrong project; AutoQA is browser-only, no audio stack.

---

## 9. How to talk about it in an interview

**Q: "Why build your own browser agent loop instead of using `browser-use`?"**
> `browser-use` is excellent for general navigation, but AutoQA's value is the QA-specific
> observation stack — ARIA snapshot + axe-core + console/network capture + structured bug reports
> with boxed evidence — plus explicit safety rails and free-tier cost control. Building the loop
> myself proves I understand observe→decide→act→verify, not that I can `pip install` a framework.

**Q: "How do you prevent the agent from doing dangerous things on a real website?"**
> Layered rails: a registrable-domain allowlist enforced at navigation and in a Playwright route
> guard; read-only-by-default tools (`click` refuses submit controls); only `submit` is a write
> action and it `interrupt()`s for human approval; a credential guard refuses card/SSN-shaped
> values and real passwords off known test hosts. Violations return `"ERROR: …"` strings the agent
> reads — they never throw or bypass the gate.

**Q: "How do you know the eval numbers are honest?"**
> The final verdict is decided in code (`decide_verdict`), not the LLM's claim — any functional
> finding means fail. The auditor can add findings but can't launder one away. For ground truth I
> built a seeded-bugs demo site at `/demo` with exact expected findings. Recall 100% on planted bugs;
> precision is honestly lower because the agent also reports real a11y issues not in the minimal
> ground-truth set — that's the expected trade-off for a QA agent tuned to catch bugs.

**Q: "Why ARIA role/name instead of CSS selectors or numbered overlays?"**
> Role/name is text-first — the model chooses from things that verifiably exist in the snapshot.
> It survives dynamic class/id churn on SPAs and fails with a readable error instead of a
> mis-click. Set-of-marks overlays need an injected overlay + mark→element map kept in sync across
> navigations, and need higher vision precision than the free Flash tier reliably gives.

---

## 10. Stretch goals / next steps

**Still free-tier:**
- **CI eval gate** — run `eval/run_eval.py --only demo` in GitHub Actions; fail the PR if
  verdict accuracy or recall drops (SpendLens capstone pattern).
- **More eval scenarios** — expand `dataset.json` with your own seeded-bugs pages.
- **Set-of-marks overlay mode** — optional numbered overlays for sites where ARIA snapshots are sparse.
- **Multi-tab / popup handling** — extend session registry to track secondary pages.
- **PDF export** — printable bug report from `ReportView` (print CSS already close).

**Production path:**
- **Auth + multi-tenancy** — Clerk/NextAuth; Postgres with row-level security for run history.
- **Scheduled regression runs** — cron against staging URLs; Slack/email on new functional findings.
- **Paid vision model** — swap `VISION_MODEL` in `.env` for higher step accuracy on complex UIs.
- **Parallel workers** — one Chromium per worker process; queue runs via Redis/Celery (Chromium is
  ~200–400 MB RAM each — plan capacity accordingly).
- **Jira/Linear integration** — MCP tool or webhook that files a ticket from each `Finding`.

**The through-line:** the free build proves the hard engineering — vision-grounded action loop,
QA observation stack, safety rails, eval rigor, and failure handling. Productionizing is
swapping the vision model, adding auth/metering, and pointing it at your staging URLs — the
loop and report schema stay the same.
