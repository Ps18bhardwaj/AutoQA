# AutoQA — Autonomous Browser QA Agent

Point it at any public URL, type a test scenario in **plain English** ("log in as standard_user, add the cheapest item to the cart, the cart badge must show 1"), and watch an agent **drive a real browser**, verify the flow, and produce a **structured bug report with annotated screenshots**. Built on **free-tier models only** — `gemini-3.5-flash` (vision) for the decisions, Playwright driving headless Chromium, axe-core for accessibility, all through the vendored LiteLLM router.

> **Why this project exists:** computer-use / browser agents are 2026's fastest-growing agent category, and the interesting engineering isn't "call a vision model in a loop" — it's the **vision-grounded action loop** (observe → decide → act → verify), the **observation stack** (accessibility tree + screenshot + console/network/axe capture), and above all **agent safety**: a domain allowlist, read-only-by-default actions, a **human-approval gate before any form submission**, and a credential guard that refuses to type real passwords or payment data. AutoQA builds the loop itself (no `browser-use` wrapper) so all of that is explicit and inspectable.

**Resume bullet:**
> Built an autonomous browser QA agent: a hand-built LangGraph observe→decide→act→verify loop where a vision LLM (`gemini-3.5-flash`) drives Playwright via a typed, whitelisted action set grounded in the page's ARIA snapshot; per-page axe-core / console / network / broken-link checks; a Pydantic bug report with severity, repro steps, and red-boxed screenshot evidence; safety rails (domain allowlist, read-only default, human-approval gate on form submission, credential guard); durable SQLite run history with a live streamed "agent viewport" UI; and a 22-scenario eval scoring bug-detection precision/recall, verdict accuracy, and action-success — all free-tier.

---

## Architecture

```
┌────────────────── React + Vite frontend ──────────────────┐        ┌──────────────────── FastAPI backend ─────────────────────┐
│  ScenarioForm (URL + scenario + max steps + sample chips)  │        │  LangGraph state machine (per-run, durably checkpointed) │
│  AgentViewport ── live streamed screenshots (SSE) ─────────│  POST  │                                                          │
│  AgentTrace ── thoughts / actions / observations / findings│  /run  │   START → bootstrap → observe → decide ─┬─ act ──┐       │
│  ApprovalModal ── form-submission gate (+ screenshot)      │◀──SSE──│                        ▲               │        │       │
│  ReportView ── verdict + findings + boxed evidence + log   │  /resume│                       │   (submit?)   ├─ approval ─interrupt
│  RunsMenu ── browsable/replayable history                  │────────▶│                       └───(act)───────┘        │(pause)  │
└────────────────────────────────────────────────────────────┘        │                        └─(finish|blocked|limit|loop)─▶ verify → END
                          ▲   /runs/<id>/step_N.png  (screenshots)      │                                                          │
                          └───────────────────────────────────────────│  browser/  session (Playwright async, 1 context/run)     │
                                                                       │            tools   (navigate/click/type/submit/assert…)   │
                                                                       │            checks  (axe + console + network + links)      │
                                                                       │            annotate (Pillow red-box on evidence)          │
                                                                       │  agent/    graph · guards (loop/no-progress) · prompts     │
                                                                       │  report.py (Finding/Report + code-decided verdict)         │
                                                                       │  safety.py (allowlist · credential guard · block detect)   │
                                                                       │  shared/llm.py  Gemini vision decide-chain (+ Flash-Lite)  │
                                                                       └──────────────────────────────────────────────────────────┘
```

### The agent loop (`backend/app/agent/graph.py`)
- **bootstrap** — create an isolated Playwright `BrowserContext`+`Page` for the run, navigate to the start URL (allowlist-checked).
- **observe** — capture the page's **ARIA snapshot** (`page.locator("body").aria_snapshot()`) + a **screenshot** (streamed to the UI). On each *new* URL: run an **axe-core** accessibility scan, a broken-image sweep, and a capped same-domain dead-link check. Every step: drain **console errors** and **failed network requests** into findings. Detect CAPTCHAs / auth walls.
- **decide** — one **vision** LLM call (`gemini-3.5-flash`): scenario + history + ARIA snapshot text + the screenshot (as a JPEG data-URL). Returns strict JSON — either an action or a finish verdict. Loop-detection and a no-progress detector short-circuit runaway runs; a premature-finish guard blocks "pass" with zero actions.
- **act** — dispatch one typed action; the result becomes an observation. Actions **never raise** — a bad selector or timeout returns `"ERROR: …"` the agent reads and adapts to.
- **approval** — if the action is a **form submission**, the graph `interrupt()`s and the UI shows an approval dialog (with a screenshot of what's about to be submitted); `/resume` continues via `Command(resume=…)`.
- **verify** — assemble the report. Failed assertions + the decide-node's reported failures + an **auditor LLM pass** feed the findings; the **final verdict is decided in code** (`report.decide_verdict`), so the model can *add* findings but can never launder a functional failure into a pass.

### Element targeting: ARIA `{role, name}`, not CSS
The decide model picks elements by the **accessible role + name it just saw in the snapshot** → `page.get_by_role(role, name=name)` with a `get_by_text` fallback. This survives dynamic class/id churn (an explicit requirement), can't produce a selector-syntax error, and keeps the screenshot for *visual context and evidence* rather than pixel-coordinate clicking.

---

## Decisions & trade-offs

- **Built the loop myself instead of wrapping `browser-use`.** `browser-use` is the closest off-the-shelf equivalent (also Playwright-backed) and is excellent for general navigation. AutoQA rolls its own loop because the *point* is the QA-specific observation stack — ARIA snapshot + axe-core + console/network capture + boxed-evidence bug reports — plus explicit safety rails and free-tier cost control, none of which a generic navigation agent exposes. Building it also *is* the portfolio signal: it demonstrates I understand the observe→decide→act→verify loop, not that I can `pip install` one.
- **ARIA role/name targeting over CSS selectors or set-of-marks overlays.** Role/name is text-first (the model chooses from things that verifiably exist in the snapshot), resilient to dynamic selectors, and fails with a readable error instead of a mis-click. Set-of-marks (numbered overlays) needs an injected overlay + a mark→element map kept in sync across navigations + higher vision precision than the free Flash tier reliably gives.
- **The final verdict is decided by code, not the LLM.** `decide_verdict()`: a `blocked_reason` ⇒ blocked; any **functional** finding ⇒ fail; otherwise pass (non-functional findings are still listed — "the flow passed, but the page has other bugs"). The auditor LLM can only *add* findings. This is what makes the eval's precision/recall trustworthy and stops a model from declaring success over a failed assertion. (Caught a real bug during the build: the auditor was laundering incidental a11y/network noise into `critical/functional` findings and flipping passing scenarios to FAIL — fixed by tightening the auditor to only report scenario-requirement failures.)
- **Screenshots stream as URLs, never base64-in-SQLite.** Each step's PNG is written to `runs/<id>/step_N.png` and served by `StaticFiles`; the SSE `screenshot` event carries the URL, and replay reads the same files. Keeps the event log (and the DB) small and makes the live viewport a plain `<img>`.
- **Third-party noise is filtered; dead links are GET-confirmed.** Console/network findings from a *different registrable domain* than the page (e.g. `backtrace.io` telemetry 401s on saucedemo) are dropped — they're not the site-under-test's bug. Dead-link HEAD failures are re-checked with GET before reporting, since many SPAs 404 on HEAD for routes that GET serves. a11y findings are capped at the top 10 by impact. Together these keep precision from drowning in advisory noise.
- **Registrable-domain allowlist via a last-two-labels heuristic** (no `tldextract` dependency / PSL fetch). It over-blocks some ccTLDs (`example.co.uk` → `co.uk`) — the *safe* failure direction for an agent that should stay on the site under test.
- **Read-only by default; only `submit` is a write action.** `click` refuses form-submit controls (pointing the agent at the approval-gated `submit`); pressing Enter in a form is dynamically gated too. The credential guard **always** refuses card/SSN-shaped values, and only allows password-like fields on known test hosts or with known test credentials.
- **One Chromium, one context per run.** The browser launches once (lifespan); each run gets an isolated `BrowserContext` so cookies don't leak between runs. LangGraph state holds only the `run_id` (Playwright objects aren't checkpoint-serializable); the live page lives in a session registry keyed by that id.

## Known limitations
- A backend restart kills the live browser of a **paused** run — the checkpoint survives but the page doesn't, so `/resume` on a dropped session returns a clean "session expired" (documented, handled). Completed runs replay fully from disk.
- The registrable-domain allowlist heuristic over-blocks multi-label public suffixes (`.co.uk`, `.com.au`).
- Vision decisions are one Gemini free-tier call per step (~15 RPM). Long runs and back-to-back evals hit rate limits; the router retries with backoff and falls back to Flash-Lite, but the free tier makes big eval sweeps slow.
- No auth on the API; single-tenant SQLite. Add auth before any public deploy.
- The WER/latency-style micro-benchmarks aren't relevant here; the eval focuses on bug-detection quality (below).

---

## Evaluation

A 19-scenario suite ([`backend/eval/dataset.json`](backend/eval/dataset.json)) across **saucedemo.com**, **the-internet.herokuapp.com**, and a **local seeded-bugs mini-site** the backend serves at `/demo` (deterministic ground truth: a total-that-doesn't-update functional bug, a broken image, a console error, a failed request, an a11y violation, plus a clean-page control). The harness drives the real graph, **auto-approves** the form-submission gate (it plays the human), and scores **verdict accuracy**, **findings precision/recall** (category + keyword match), and **action-success rate**.

Committed numbers are the **deterministic `/demo` subset** (where ground truth is exact):

| Metric | Result |
|--------|-------:|
| Verdict accuracy | **100%** (4/4) |
| Findings recall | **100%** (5/5) |
| Findings precision | **36%** (5/14) |
| Action-success rate | **100%** |

The agent caught **every planted bug** (recall 100%), the clean-page control produced **zero** findings, and the human-approved checkout flow passed. Precision (36%) is dragged by the home page's *real* accessibility issues beyond the one planted contrast bug — legitimately reported, but not in the minimal ground-truth set. Full breakdown + honest reading in [`eval/results.md`](backend/eval/results.md).

```bash
cd backend
python eval/run_eval.py --only demo     # deterministic subset -> eval/results.md
python eval/run_eval.py                 # full 19-scenario suite (real sites; free-tier slow)
```
> The eval calls live models (and the real internet), so numbers are generated on your machine from your free keys — not pre-baked. The harness, dataset, scoring, and report are all here; one command fills in `eval/results.md`.

### Tests
A keyless `pytest` suite (`backend/tests/`) — **no API keys needed**; browser tests auto-skip without Chromium:
```bash
cd backend
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt
python -m pytest -q                 # 46 keyless: report/verdict rules, safety (allowlist+credential guard),
                                    # loop/no-progress guards, check converters, API history CRUD
python -m pytest -q -m browser      # 11 with real Chromium vs the local /demo site, incl. a FULL graph
                                    # run with a stubbed decide node (whole loop, zero LLM calls)
```

---

## Run it locally

> **Self-contained.** The LLM router + tracing are vendored under `backend/shared/`, and `axe.min.js` + the demo site are bundled — AutoQA needs nothing outside `4-autoqa/`. SQLite is a file; no database service.

**Prerequisites:** Python 3.11, Node 20+, and a free **Gemini** key ([AI Studio](https://aistudio.google.com/app/apikey)). Copy `.env.example` → `.env` here and add `GEMINI_API_KEY`.

```bash
# 1. Backend
cd 4-autoqa/backend
uv venv .venv && uv pip install --python .venv/Scripts/python.exe -r requirements.txt
./.venv/Scripts/playwright.exe install chromium          # one-time (~150MB)
./.venv/Scripts/python.exe scripts/smoke_browser.py      # go/no-go: chromium + aria + axe work
./.venv/Scripts/uvicorn app.api.main:app --reload --port 8003   # http://localhost:8003/docs

# 2. Frontend (new terminal)
cd ../frontend
npm install
npm run dev                                              # http://localhost:5173
```

Open the app, click a **sample chip** (or enter a URL + scenario), and hit **Run QA**. Watch the live agent viewport beside the reasoning trace; if the scenario needs a form submitted, an **approval dialog** appears with a screenshot of what's about to happen — approve it and the run finishes with a verdict, findings, and red-boxed screenshot evidence. Open **Runs** in the header to replay any past run.

**Try the agent from the CLI (no frontend):**
```bash
cd backend && ./.venv/Scripts/python.exe scripts/run_scenario.py \
  --url https://www.saucedemo.com \
  --scenario "Log in as standard_user / secret_sauce and confirm the inventory page loads."
```

## Deploy (free tier)
- **Backend** → **HF Spaces (Docker)** via [`backend/Dockerfile`](backend/Dockerfile) (built on Microsoft's Playwright Python image — Chromium preinstalled). **Not Render's 512MB free tier** — Chromium needs ≥1GB RAM. Mount a volume for `autoqa.db`/`runs/` if the platform's filesystem doesn't persist.
- **Frontend** → Vercel; set `VITE_API_BASE` and `VITE_API_ORIGIN` to the backend origin (the latter so streamed screenshots load cross-origin), and add the Vercel origin to `CORS_ORIGINS`.
- **Tracing** → set `LANGFUSE_*` to trace every vision/audit call.

## API

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/run` | Start a QA run `{url, scenario, max_steps}`; streams the trace + screenshots as SSE |
| POST | `/resume` | Approve/reject a paused form submission; streams the rest |
| GET | `/history` | List past runs (scenario, verdict, findings count) |
| GET | `/history/{id}` | Full persisted event log for one run (replay) |
| DELETE | `/history/{id}` | Remove a run + its screenshots |
| GET | `/runs/{id}/step_N.png` | Streamed/stored screenshots (StaticFiles) |
| GET | `/demo/*` | The bundled seeded-bugs mini-site |
| GET | `/health` | Backend + Chromium readiness |
