"""Bug-report models + the deterministic merge/verdict rules.

The LLM proposes scenario-level failures, but the final verdict and the
finding list are assembled by CODE here — the model can add findings, it can
never launder one away. That separation is what makes the eval's
precision/recall numbers meaningful.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    INFO = "info"


class Category(str, Enum):
    FUNCTIONAL = "functional"
    CONSOLE = "console"
    NETWORK = "network"
    BROKEN_LINK = "broken-link"
    A11Y = "a11y"
    BLOCKED = "blocked"


# axe-core impact -> our severity (critical/serious surface as real bugs;
# moderate/minor are advisory).
AXE_IMPACT_SEVERITY: dict[str, Severity] = {
    "critical": Severity.MAJOR,
    "serious": Severity.MAJOR,
    "moderate": Severity.MINOR,
    "minor": Severity.INFO,
}


class Evidence(BaseModel):
    screenshot_url: str | None = None
    boxed: bool = False                 # True if the failing element is boxed in the image
    element: str | None = None          # e.g. "role=button name='Checkout'"


class Finding(BaseModel):
    id: str                             # "f1", "f2", ...
    severity: Severity
    category: Category
    title: str
    expected: str
    actual: str
    page_url: str
    repro_steps: list[str] = Field(default_factory=list)
    evidence: Evidence | None = None


class ActionLogEntry(BaseModel):
    step: int
    thought: str
    tool: str
    args: dict
    observation: str
    page_url: str
    ok: bool                            # False when the observation is an ERROR/ASSERTION FAILED


class Stats(BaseModel):
    steps: int = 0
    actions_ok: int = 0
    actions_error: int = 0
    pages_visited: int = 0
    findings_by_category: dict[str, int] = Field(default_factory=dict)
    duration_s: float = 0.0


class Report(BaseModel):
    scenario: str
    start_url: str
    verdict: Literal["pass", "fail", "blocked"]
    summary: str
    findings: list[Finding]
    action_log: list[ActionLogEntry]
    stats: Stats


def merge_findings(findings: list[Finding], *, a11y_cap: int = 10) -> list[Finding]:
    """Dedupe by (category, title, page_url) and cap a11y findings at the top
    N by severity — axe can emit dozens of near-identical advisory hits that
    would otherwise drown the functional bugs."""
    seen: set[tuple[str, str, str]] = set()
    deduped: list[Finding] = []
    for f in findings:
        key = (f.category.value, f.title, f.page_url)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(f)

    a11y = [f for f in deduped if f.category is Category.A11Y]
    if len(a11y) > a11y_cap:
        order = {Severity.CRITICAL: 0, Severity.MAJOR: 1, Severity.MINOR: 2, Severity.INFO: 3}
        keep = set(id(f) for f in sorted(a11y, key=lambda f: order[f.severity])[:a11y_cap])
        deduped = [f for f in deduped if f.category is not Category.A11Y or id(f) in keep]
    return deduped


def decide_verdict(findings: list[Finding], *, blocked_reason: str | None) -> str:
    """The verdict rule, in code — not the LLM's claim:
    blocked_reason ⇒ blocked; any functional finding ⇒ fail; otherwise pass
    (non-functional findings are still listed: 'the scenario passed, but the
    page has other bugs')."""
    if blocked_reason:
        return "blocked"
    if any(f.category is Category.FUNCTIONAL for f in findings):
        return "fail"
    return "pass"


def renumber(findings: list[Finding]) -> list[Finding]:
    """Stable f1..fN ids after merge."""
    for i, f in enumerate(findings, start=1):
        f.id = f"f{i}"
    return findings


def repro_steps_from_log(log: list[ActionLogEntry], up_to_step: int | None = None) -> list[str]:
    """Render the action log (up to the discovery step) as human repro steps."""
    steps: list[str] = []
    for entry in log:
        if up_to_step is not None and entry.step > up_to_step:
            break
        args = entry.args or {}
        if entry.tool == "navigate":
            steps.append(f"Navigate to {args.get('url', '?')}")
        elif entry.tool == "click":
            steps.append(f"Click the {args.get('role', 'element')} \"{args.get('name', '?')}\"")
        elif entry.tool == "type_text":
            steps.append(f"Type \"{args.get('text', '')}\" into {args.get('role', 'field')} \"{args.get('name', '?')}\"")
        elif entry.tool == "select_option":
            steps.append(f"Select \"{args.get('value', '?')}\" in {args.get('role', 'combobox')} \"{args.get('name', '?')}\"")
        elif entry.tool == "press_key":
            steps.append(f"Press {args.get('key', '?')}")
        elif entry.tool == "scroll":
            steps.append(f"Scroll {args.get('direction', 'down')}")
        elif entry.tool == "go_back":
            steps.append("Go back")
        elif entry.tool == "submit":
            steps.append(f"Submit via the {args.get('role', 'button')} \"{args.get('name', '?')}\"")
        elif entry.tool.startswith("assert"):
            steps.append(f"Check: {args.get('text') or args.get('name') or '?'}")
    return steps
