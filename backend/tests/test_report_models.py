"""Keyless tests for the report models + deterministic verdict/merge rules."""
from app.report import (
    Category, Evidence, Finding, Severity,
    decide_verdict, merge_findings, renumber, repro_steps_from_log, ActionLogEntry,
)


def _f(cat, title="t", sev=Severity.MINOR, page="p"):
    return Finding(id="f0", severity=sev, category=cat, title=title,
                   expected="e", actual="a", page_url=page)


def test_verdict_functional_finding_is_fail():
    assert decide_verdict([_f(Category.FUNCTIONAL)], blocked_reason=None) == "fail"


def test_verdict_only_nonfunctional_is_pass_with_findings():
    findings = [_f(Category.CONSOLE), _f(Category.A11Y)]
    assert decide_verdict(findings, blocked_reason=None) == "pass"


def test_verdict_blocked_wins_over_everything():
    assert decide_verdict([_f(Category.FUNCTIONAL)], blocked_reason="captcha") == "blocked"


def test_verdict_clean_page_passes():
    assert decide_verdict([], blocked_reason=None) == "pass"


def test_merge_dedupes_by_category_title_page():
    dupes = [_f(Category.CONSOLE, "same"), _f(Category.CONSOLE, "same"), _f(Category.CONSOLE, "other")]
    merged = merge_findings(dupes)
    assert len(merged) == 2


def test_merge_caps_a11y_by_severity():
    a11y = [_f(Category.A11Y, f"rule-{i}", sev=Severity.INFO) for i in range(15)]
    a11y += [_f(Category.A11Y, "important", sev=Severity.MAJOR)]
    merged = merge_findings(a11y, a11y_cap=10)
    kept = [f for f in merged if f.category is Category.A11Y]
    assert len(kept) == 10
    # the MAJOR one must survive the cap
    assert any(f.title == "important" for f in kept)


def test_merge_does_not_cap_functional():
    many = [_f(Category.FUNCTIONAL, f"bug-{i}") for i in range(15)]
    assert len(merge_findings(many, a11y_cap=10)) == 15


def test_renumber_is_stable():
    findings = [_f(Category.CONSOLE, f"t{i}") for i in range(3)]
    renumber(findings)
    assert [f.id for f in findings] == ["f1", "f2", "f3"]


def test_repro_steps_render_from_log():
    log = [
        ActionLogEntry(step=0, thought="", tool="navigate", args={"url": "http://x"},
                       observation="ok", page_url="http://x", ok=True),
        ActionLogEntry(step=1, thought="", tool="click", args={"role": "button", "name": "Add"},
                       observation="ok", page_url="http://x", ok=True),
    ]
    steps = repro_steps_from_log(log)
    assert steps == ["Navigate to http://x", 'Click the button "Add"']


def test_repro_steps_respect_up_to_step():
    log = [
        ActionLogEntry(step=0, thought="", tool="navigate", args={"url": "http://x"},
                       observation="ok", page_url="http://x", ok=True),
        ActionLogEntry(step=1, thought="", tool="scroll", args={"direction": "down"},
                       observation="ok", page_url="http://x", ok=True),
    ]
    assert len(repro_steps_from_log(log, up_to_step=0)) == 1


def test_evidence_defaults():
    ev = Evidence(screenshot_url="/runs/x/step_001.png")
    assert ev.boxed is False and ev.element is None
