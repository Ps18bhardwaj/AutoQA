"""Convert raw browser observations (console/network buffers, axe results,
broken-image/link sweeps) into structured Findings.

Pure mapping functions where possible (unit-tested keyless with plain dicts);
the page-touching sweeps (axe, links, images) are thin async helpers.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx

from ..config import get_settings
from ..report import AXE_IMPACT_SEVERITY, Category, Evidence, Finding, Severity

logger = logging.getLogger("autoqa.checks")


def _next_id(counter: list[int]) -> str:
    counter[0] += 1
    return f"f{counter[0]}"


# ---- buffer -> Finding converters (pure) ----------------------------------
def console_findings(entries: list[dict], counter: list[int]) -> list[Finding]:
    out = []
    for e in entries:
        is_error = e.get("type") == "error"
        out.append(Finding(
            id=_next_id(counter),
            severity=Severity.MINOR if not is_error else Severity.MAJOR,
            category=Category.CONSOLE,
            title=f"Console {e.get('type', 'error')}: {e.get('text', '')[:80]}",
            expected="No console errors on a healthy page",
            actual=e.get("text", "")[:300],
            page_url=e.get("page_url", ""),
        ))
    return out


def pageerror_findings(entries: list[dict], counter: list[int]) -> list[Finding]:
    return [Finding(
        id=_next_id(counter),
        severity=Severity.MAJOR,
        category=Category.CONSOLE,
        title=f"Uncaught JS error: {e.get('text', '')[:80]}",
        expected="No uncaught JavaScript exceptions",
        actual=e.get("text", "")[:300],
        page_url=e.get("page_url", ""),
    ) for e in entries]


def _same_site(url: str, page_url: str) -> bool:
    """True if url and page_url share a registrable domain — used to drop
    third-party noise (analytics/telemetry 401s aren't the site's own bug)."""
    from .. import safety
    a = safety.registrable_suffix(urlparse(url).hostname or "")
    b = safety.registrable_suffix(urlparse(page_url).hostname or "")
    return bool(a) and a == b


def network_findings(failed: list[dict], http_errors: list[dict], counter: list[int]) -> list[Finding]:
    out = []
    for e in failed:
        if not _same_site(e.get("url", ""), e.get("page_url", "")):
            continue  # third-party request failure — not the site-under-test's bug
        out.append(Finding(
            id=_next_id(counter),
            severity=Severity.MINOR,
            category=Category.NETWORK,
            title=f"Request failed: {_short_url(e.get('url', ''))}",
            expected="All network requests complete",
            actual=f"{e.get('method', 'GET')} {e.get('url', '')} — {e.get('failure', 'failed')}",
            page_url=e.get("page_url", ""),
        ))
    for e in http_errors:
        if not _same_site(e.get("url", ""), e.get("page_url", "")):
            continue
        status = e.get("status", 0)
        out.append(Finding(
            id=_next_id(counter),
            severity=Severity.MAJOR if status >= 500 else Severity.MINOR,
            category=Category.NETWORK,
            title=f"HTTP {status}: {_short_url(e.get('url', ''))}",
            expected="Resources load with a 2xx/3xx status",
            actual=f"{e.get('url', '')} returned {status}",
            page_url=e.get("page_url", ""),
        ))
    return out


def axe_findings(violations: list[dict], page_url: str, counter: list[int]) -> list[Finding]:
    out = []
    for v in violations:
        impact = (v.get("impact") or "minor").lower()
        severity = AXE_IMPACT_SEVERITY.get(impact, Severity.INFO)
        nodes = v.get("nodes", [])
        target = ""
        if nodes:
            tsel = nodes[0].get("target", [])
            target = tsel[0] if tsel else ""
        out.append(Finding(
            id=_next_id(counter),
            severity=severity,
            category=Category.A11Y,
            title=f"a11y ({impact}): {v.get('id', '')}",
            expected=v.get("help", "Accessibility rule should pass"),
            actual=f"{v.get('description', '')[:200]}" + (f" [{target}]" if target else ""),
            page_url=page_url,
        ))
    return out


def _short_url(url: str) -> str:
    p = urlparse(url)
    path = p.path or "/"
    return f"{p.netloc}{path}"[:70]


# ---- page-touching sweeps (async) -----------------------------------------
async def run_axe(page) -> list[dict]:
    """Inject vendored axe-core and return the violations list. Never raises."""
    settings = get_settings()
    try:
        await page.add_script_tag(path=str(settings.axe_js_path))
        results = await page.evaluate("async () => await axe.run()")
        return results.get("violations", [])
    except Exception as e:  # pragma: no cover - page-dependent
        logger.warning("[checks] axe scan failed: %s", str(e)[:150])
        return []


async def broken_image_findings(page, counter: list[int]) -> list[Finding]:
    """Find <img> elements that failed to load (naturalWidth === 0)."""
    try:
        broken = await page.evaluate("""() => {
            return Array.from(document.images)
                .filter(img => img.complete && img.naturalWidth === 0)
                .map(img => img.currentSrc || img.src)
                .slice(0, 20);
        }""")
    except Exception:  # pragma: no cover
        return []
    return [Finding(
        id=_next_id(counter),
        severity=Severity.MINOR,
        category=Category.BROKEN_LINK,
        title=f"Broken image: {_short_url(src)}",
        expected="All images load",
        actual=f"Image failed to load (naturalWidth=0): {src}",
        page_url=page.url,
    ) for src in broken]


async def dead_link_findings(page, allowlist: set[str], counter: list[int]) -> list[Finding]:
    """HEAD-check up to N same-allowlist anchors on the page; report >=400."""
    from .. import safety
    settings = get_settings()
    try:
        hrefs = await page.evaluate("""() => Array.from(document.querySelectorAll('a[href]'))
            .map(a => a.href).filter(h => h.startsWith('http'))""")
    except Exception:  # pragma: no cover
        return []

    seen: set[str] = set()
    to_check: list[str] = []
    for h in hrefs:
        if h in seen or not safety.is_allowed(h, allowlist):
            continue
        seen.add(h)
        to_check.append(h)
        if len(to_check) >= settings.link_check_max_per_page:
            break

    out: list[Finding] = []
    async with httpx.AsyncClient(follow_redirects=True, timeout=8.0) as client:
        for url in to_check:
            try:
                resp = await client.head(url)
                # Many servers/SPAs misroute or reject HEAD (405/404 on a route
                # that GET serves fine) — confirm any HEAD failure with a GET so
                # we don't report false-positive dead links.
                if resp.status_code >= 400:
                    resp = await client.get(url)
                if resp.status_code >= 400:
                    out.append(Finding(
                        id=_next_id(counter),
                        severity=Severity.MINOR,
                        category=Category.BROKEN_LINK,
                        title=f"Dead link (HTTP {resp.status_code}): {_short_url(url)}",
                        expected="Links resolve with a 2xx/3xx status",
                        actual=f"{url} returned {resp.status_code}",
                        page_url=page.url,
                    ))
            except Exception:
                out.append(Finding(
                    id=_next_id(counter),
                    severity=Severity.MINOR,
                    category=Category.BROKEN_LINK,
                    title=f"Unreachable link: {_short_url(url)}",
                    expected="Links resolve",
                    actual=f"{url} could not be reached",
                    page_url=page.url,
                ))
    return out
