"""Safety rails: domain allowlist, credential guard, CAPTCHA/auth-wall detection.

All pure functions (no Playwright, no LLM) so every branch is keyless-testable.
The rails run INSIDE the tools (never-raise contract: violations come back as
"ERROR: ..." observation strings the agent can read and adapt to).
"""
from __future__ import annotations

import re
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Domain allowlist
# ---------------------------------------------------------------------------
def registrable_suffix(host: str) -> str:
    """Last-two-labels heuristic ('app.saucedemo.com' -> 'saucedemo.com').

    Deliberately NOT tldextract (extra dep + PSL fetch at import). The
    trade-off: some ccTLD sites ('example.co.uk') collapse to 'co.uk' and the
    allowlist check therefore OVER-blocks their sibling subdomains — the safe
    failure direction for a QA agent. Documented in the README.
    """
    parts = host.lower().strip(".").split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host.lower()


def build_allowlist(start_url: str, extra_hosts: list[str]) -> set[str]:
    """Hosts + registrable suffixes the agent may navigate to."""
    allow: set[str] = {"localhost", "127.0.0.1"}
    host = (urlparse(start_url).hostname or "").lower()
    if host:
        allow.add(host)
        allow.add(registrable_suffix(host))
    for h in extra_hosts:
        h = h.lower().strip()
        if h:
            allow.add(h)
            allow.add(registrable_suffix(h))
    return allow


def is_allowed(url: str, allowlist: set[str]) -> bool:
    """A URL is allowed if its host or the host's registrable suffix is listed."""
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    return host in allowlist or registrable_suffix(host) in allowlist


# ---------------------------------------------------------------------------
# Credential guard (used by the type_text tool)
# ---------------------------------------------------------------------------
# Hard-refuse patterns — never typed anywhere, no exceptions.
_CARD_RE = re.compile(r"\b\d{13,19}\b")                     # card-number-length digit run
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")              # US SSN
# Field looks credential-ish by its accessible name.
_SECRET_FIELD_RE = re.compile(r"password|passcode|\bpin\b|card|cvv|cvc|account number|ssn", re.I)


def credential_verdict(
    *,
    value: str,
    field_name: str,
    is_password_input: bool,
    page_host: str,
    known_test_hosts: list[str],
    test_credentials: list[str],
) -> str | None:
    """Return an ERROR string if typing must be refused, else None (allowed).

    1. Card/SSN-shaped values are ALWAYS refused — even on test sites; a QA
       agent has no business typing anything that even looks like payment data.
    2. Credential-like targets (real password inputs, or fields named like
       secrets) only accept known test credentials, or anything on a known
       test host (saucedemo etc. need arbitrary usernames like 'problem_user').
    """
    if _CARD_RE.search(value) or _SSN_RE.search(value):
        return ("ERROR: refusing to type a value that looks like payment-card or "
                "SSN data. AutoQA never enters real payment or identity data.")

    credential_target = is_password_input or bool(_SECRET_FIELD_RE.search(field_name or ""))
    if not credential_target:
        return None

    host = page_host.lower()
    if host in (h.lower() for h in known_test_hosts):
        return None
    if value in test_credentials:
        return None
    return ("ERROR: refusing to type a credential-like value on a non-test site. "
            "AutoQA never enters real credentials — report the scenario as blocked "
            "if it cannot proceed without them.")


# ---------------------------------------------------------------------------
# CAPTCHA / auth-wall detection
# ---------------------------------------------------------------------------
_BLOCK_MARKERS = (
    "recaptcha", "hcaptcha", "captcha",
    "verify you are human", "verifying you are human",
    "checking your browser", "just a moment",        # Cloudflare challenge titles
    "access denied", "attention required",
)


def detect_block(aria_snapshot: str, page_title: str, main_status: int | None) -> str | None:
    """Return a human-readable blocked-reason, or None.

    Never bypass: a CAPTCHA or auth wall ends the run with verdict 'blocked'.
    """
    if main_status in (401, 403):
        return f"the page returned HTTP {main_status} (auth wall) — cannot proceed"
    haystack = f"{page_title}\n{aria_snapshot[:4000]}".lower()
    for marker in _BLOCK_MARKERS:
        if marker in haystack:
            return f"a human-verification / access barrier was detected ({marker!r}) — AutoQA never bypasses these"
    return None
