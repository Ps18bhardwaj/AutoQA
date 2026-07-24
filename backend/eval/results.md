# AutoQA eval results

Deterministic **local seeded-bugs** subset (the `/demo` scenarios), run against real
Chromium + `gemini/gemini-3.5-flash` vision. These are the scenarios with known
ground truth, so precision/recall are meaningful. Generated on this machine from
free-tier keys — **not pre-baked**. The full 19-scenario dataset (adding
saucedemo.com + the-internet.herokuapp.com for verdict-accuracy on real sites) is
runnable with `python eval/run_eval.py`; on the free Gemini tier the real-site runs
are slow and occasionally hit a transient 429/400 (the router retries + falls back to
Flash-Lite), so the committed numbers below are the deterministic core.

| Metric | Result |
|---|---:|
| Verdict accuracy | **100%** (4/4) |
| Findings recall | **100%** (5/5) |
| Findings precision | **36%** (5/14) |
| Action-success rate | **100%** |

_Precision/recall are over scenarios that declare `expected_findings` (incl. the
clean-page control with zero); info-severity a11y findings are excluded from precision
as advisory noise. Action-success excludes assertions (they're checks, not actions — a
deliberate ASSERTION FAILED on a buggy page is the tool working correctly)._

| Scenario | Verdict | Expected | ✓ | Findings tp/exp | Predicted | Time |
|---|---|---|:-:|:-:|:-:|--:|
| demo-01-total-bug | fail | fail | ✅ | 1/1 | 3 | 63s |
| demo-02-clean-control | pass | pass | ✅ | 0/0 | 0 | 35s |
| demo-03-inspect-all | pass | pass | ✅ | 4/4 | 11 | 39s |
| demo-07-checkout-approval | pass | pass | ✅ | 0/0 | 0 | 102s |

**Reading the numbers honestly:**
- **Recall 100%** — the agent caught every planted bug: the functional "total doesn't
  update" bug (demo-01), and all four planted issues on the home page (broken image,
  console error, failed network request, low-contrast a11y violation — demo-03).
- **Verdict 100%** — the functional bug correctly fails; the clean page and the
  successful checkout (which required approving a form submission) correctly pass.
- **Precision 36%** is dragged almost entirely by demo-03: the home page's real
  accessibility issues beyond the planted contrast one (missing landmark, heading
  order, region) are legitimately reported but aren't in the minimal ground-truth set,
  so they count as "false positives" against it. The clean-page control (demo-02) and
  the checkout flow (demo-07) both produced **zero** findings — the agent doesn't
  invent problems where there are none. This is the expected precision/recall trade-off
  for a QA agent tuned to catch bugs; the a11y cap + third-party-network filter keep it
  from being worse.
