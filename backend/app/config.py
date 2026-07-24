"""AutoQA configuration (env-driven, free-tier defaults)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py lives at 4-autoqa/backend/app/config.py:
#   parents[1] = 4-autoqa/backend   parents[2] = 4-autoqa
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# pydantic-settings' env_file only populates this Settings class's own
# declared fields — it does not inject values into os.environ. Provider
# SDKs (litellm's Gemini key lookup) read GEMINI_API_KEY/GOOGLE_API_KEY
# straight from os.environ, so load the same .env files into the real
# process environment too. Project-root .env wins; backend/.env fills gaps.
load_dotenv(_PROJECT_ROOT / ".env")
load_dotenv(_BACKEND_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_PROJECT_ROOT / ".env", _BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Vision LLM (decisions need image input — Groq has no vision, so the
    # --- decide chain is Gemini-only; both tiers have separate free quotas) ---
    vision_model: str = "gemini/gemini-3.5-flash"
    vision_fallback: str = "gemini/gemini-3.1-flash-lite"
    # Text-only calls (the verify-node auditor) can use the full default chain.
    text_model: str = "gemini/gemini-3.5-flash"

    # --- Agent limits ---
    agent_max_steps: int = 12          # UI offers 8/12/20; hard server cap below
    agent_max_steps_cap: int = 25
    aria_max_chars: int = 8000         # snapshot truncation for the decide prompt
    decide_max_tokens: int = 1200

    # --- Browser ---
    headless: bool = True
    nav_timeout_ms: int = 15_000
    action_timeout_ms: int = 5_000
    viewport_width: int = 1280
    viewport_height: int = 800
    session_idle_reap_s: int = 900     # close browser sessions unused this long

    # --- Safety ---
    allowlist_extra: str = ""                       # comma-separated extra allowed hosts
    known_test_hosts: str = ",".join([
        "www.saucedemo.com", "saucedemo.com",
        "the-internet.herokuapp.com", "localhost", "127.0.0.1",
    ])
    test_credentials: str = ",".join(["secret_sauce", "SuperSecretPassword!"])

    # --- Checks ---
    link_check_max_per_page: int = 20  # cap same-domain link HEAD checks
    a11y_max_findings: int = 10        # cap axe findings per report (top by impact)

    # --- API ---
    autoqa_api_port: int = 8003
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Persistence (runs + events; shared with the LangGraph checkpointer) ---
    agent_db: str = "autoqa.db"
    runs_dir: str = "runs"             # per-run screenshot folders (gitignored)
    runs_keep: int = 50                # startup sweep keeps the newest N run folders

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def backend_root(self) -> Path:
        return _BACKEND_ROOT

    @property
    def agent_db_path(self) -> Path:
        p = Path(self.agent_db)
        return p if p.is_absolute() else _BACKEND_ROOT / p

    @property
    def runs_dir_path(self) -> Path:
        p = Path(self.runs_dir)
        return p if p.is_absolute() else _BACKEND_ROOT / p

    @property
    def demo_site_dir(self) -> Path:
        return _BACKEND_ROOT / "app" / "demo_site"

    @property
    def axe_js_path(self) -> Path:
        return _BACKEND_ROOT / "app" / "browser" / "vendor" / "axe.min.js"

    @property
    def allowlist_extra_hosts(self) -> list[str]:
        return [h.strip().lower() for h in self.allowlist_extra.split(",") if h.strip()]

    @property
    def known_test_host_list(self) -> list[str]:
        return [h.strip().lower() for h in self.known_test_hosts.split(",") if h.strip()]

    @property
    def test_credential_list(self) -> list[str]:
        return [c.strip() for c in self.test_credentials.split(",") if c.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
