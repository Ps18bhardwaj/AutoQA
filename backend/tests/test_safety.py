"""Keyless tests for the safety rails: allowlist, credential guard, block detector."""
from app import safety


# ---- allowlist ------------------------------------------------------------
def test_registrable_suffix():
    assert safety.registrable_suffix("www.saucedemo.com") == "saucedemo.com"
    assert safety.registrable_suffix("saucedemo.com") == "saucedemo.com"
    assert safety.registrable_suffix("a.b.c.example.com") == "example.com"


def test_allowlist_includes_start_host_subdomains_and_localhost():
    allow = safety.build_allowlist("https://www.saucedemo.com/inventory", [])
    assert safety.is_allowed("https://www.saucedemo.com/cart", allow)
    assert safety.is_allowed("https://saucedemo.com/", allow)          # registrable suffix
    assert safety.is_allowed("https://shop.saucedemo.com/", allow)     # sibling subdomain
    assert safety.is_allowed("http://localhost:8003/demo/", allow)


def test_allowlist_blocks_other_domains():
    allow = safety.build_allowlist("https://www.saucedemo.com/", [])
    assert not safety.is_allowed("https://evil.example.com/", allow)
    assert not safety.is_allowed("https://google.com/", allow)


def test_allowlist_extra_hosts():
    allow = safety.build_allowlist("https://www.saucedemo.com/", ["api.example.com"])
    assert safety.is_allowed("https://api.example.com/x", allow)
    assert safety.is_allowed("https://example.com/x", allow)  # its registrable suffix too


def test_is_allowed_rejects_non_http_or_hostless():
    allow = safety.build_allowlist("https://www.saucedemo.com/", [])
    assert not safety.is_allowed("about:blank", allow)
    assert not safety.is_allowed("", allow)


# ---- credential guard -----------------------------------------------------
KTH = ["www.saucedemo.com", "the-internet.herokuapp.com", "localhost"]
TC = ["secret_sauce", "SuperSecretPassword!"]


def _verdict(**kw):
    base = dict(value="", field_name="", is_password_input=False,
                page_host="example.com", known_test_hosts=KTH, test_credentials=TC)
    base.update(kw)
    return safety.credential_verdict(**base)


def test_card_number_always_refused_even_on_test_host():
    assert _verdict(value="4111111111111111", page_host="www.saucedemo.com") is not None


def test_ssn_always_refused():
    assert _verdict(value="123-45-6789") is not None


def test_normal_text_in_normal_field_is_allowed():
    assert _verdict(value="hello world", field_name="search") is None


def test_password_on_test_host_allowed():
    assert _verdict(value="anything", is_password_input=True, page_host="www.saucedemo.com") is None


def test_password_on_unknown_host_refused_unless_known_credential():
    assert _verdict(value="hunter2", is_password_input=True, page_host="evil.com") is not None
    assert _verdict(value="secret_sauce", is_password_input=True, page_host="evil.com") is None


def test_credential_like_field_name_triggers_guard():
    # a field literally named "password" on an unknown host, even if not type=password
    assert _verdict(value="hunter2", field_name="Password", page_host="evil.com") is not None


# ---- block detector -------------------------------------------------------
def test_detect_block_on_401_403():
    assert safety.detect_block("", "", 401) is not None
    assert safety.detect_block("", "", 403) is not None


def test_detect_block_on_captcha_marker():
    assert safety.detect_block("- text: Please complete the reCAPTCHA", "", 200) is not None


def test_detect_block_cloudflare_title():
    assert safety.detect_block("", "Just a moment...", 200) is not None


def test_no_block_on_healthy_page():
    assert safety.detect_block("- heading: Welcome", "Home", 200) is None
