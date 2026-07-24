"""Dev server entry point (Windows-safe Playwright + uvicorn --reload).

Usage:
    python run_dev.py
"""
from __future__ import annotations

import sys

import uvicorn


from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent

def main() -> None:
    uvicorn.run(
        "app.api.main:app",
        host="127.0.0.1",
        port=8003,
        reload=True,
        reload_dirs=[str(_BACKEND_ROOT / "app")],
        reload_excludes=[".venv", "runs", "*.db*", "*.png", "*.log", "__pycache__", ".pytest_cache"],
        loop="app.asyncio_platform:loop_factory",
    )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
