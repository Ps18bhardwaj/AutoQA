"""Keyless tests for the buffer -> Finding converters (no browser)."""
from app.browser import checks
from app.report import Category, Severity


def test_console_error_maps_to_major():
    out = checks.console_findings([{"type": "error", "text": "boom", "page_url": "p"}], [0])
    assert len(out) == 1
    assert out[0].category is Category.CONSOLE
    assert out[0].severity is Severity.MAJOR


def test_console_warning_maps_to_minor():
    out = checks.console_findings([{"type": "warning", "text": "meh", "page_url": "p"}], [0])
    assert out[0].severity is Severity.MINOR


def test_pageerror_is_major():
    out = checks.pageerror_findings([{"text": "TypeError x", "page_url": "p"}], [0])
    assert out[0].severity is Severity.MAJOR
    assert out[0].category is Category.CONSOLE


def test_network_failed_and_http_errors():
    # Same-site requests (same registrable domain as the page) are reported.
    page = "https://shop.example.com/cart"
    out = checks.network_findings(
        [{"url": "https://example.com/a.js", "method": "GET", "failure": "ERR", "page_url": page}],
        [{"url": "https://api.example.com/x", "status": 500, "page_url": page},
         {"url": "https://cdn.example.com/img", "status": 404, "page_url": page}],
        [0],
    )
    assert len(out) == 3
    # 500 -> major, 404 -> minor
    assert any(f.severity is Severity.MAJOR and "500" in f.title for f in out)
    assert any(f.severity is Severity.MINOR and "404" in f.title for f in out)


def test_network_third_party_findings_are_filtered():
    page = "https://www.saucedemo.com/inventory.html"
    out = checks.network_findings(
        [],
        [{"url": "https://events.backtrace.io/api/submit", "status": 401, "page_url": page}],
        [0],
    )
    # a third-party telemetry 401 is not the site-under-test's bug
    assert out == []


def test_axe_impact_mapping():
    violations = [
        {"id": "color-contrast", "impact": "serious", "help": "contrast", "description": "d", "nodes": []},
        {"id": "landmark", "impact": "moderate", "help": "landmark", "description": "d", "nodes": []},
    ]
    out = checks.axe_findings(violations, "p", [0])
    assert out[0].severity is Severity.MAJOR   # serious
    assert out[1].severity is Severity.MINOR   # moderate
    assert all(f.category is Category.A11Y for f in out)


def test_ids_are_sequential_across_converters():
    counter = [0]
    page = "https://example.com/"
    a = checks.console_findings([{"type": "error", "text": "x", "page_url": page}], counter)
    b = checks.network_findings([], [{"url": "https://example.com/u", "status": 404, "page_url": page}], counter)
    assert a[0].id == "f1"
    assert b[0].id == "f2"
