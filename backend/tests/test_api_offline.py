"""Keyless API tests — no browser, no LLM, no real graph.

The graph/browser warmup in lifespan is stubbed so the app starts instantly;
these cover the run-history CRUD surface and /health shape.
"""
from fastapi.testclient import TestClient

from app import runs_store
from app.api import main as api_main


class _FakeSettings:
    def __init__(self, db, runs):
        self.agent_db_path = db
        self.runs_dir_path = runs
        self.demo_site_dir = runs           # unused in these tests
        self.runs_keep = 50
        self.cors_origin_list = ["*"]
        self.vision_model = "gemini/gemini-3.5-flash"


def _client(tmp_path, monkeypatch):
    db = tmp_path / "autoqa.db"
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(runs_store, "get_settings", lambda: _FakeSettings(db, runs))
    # Neutralise lifespan warmup (no chromium / no checkpoint DB needed here).

    async def _noop():
        return None

    monkeypatch.setattr(api_main.bsession, "get_browser", _noop)
    monkeypatch.setattr(api_main.bsession, "shutdown_browser", _noop)

    async def _get_graph():
        return None

    monkeypatch.setattr(api_main, "get_graph", _get_graph)

    async def _close_graph():
        return None

    monkeypatch.setattr(api_main, "close_graph", _close_graph)
    return TestClient(api_main.app)


def test_history_crud_round_trip(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        runs_store.create_run("r1", "log in and check the cart", "https://www.saucedemo.com")
        runs_store.finish_run("r1", "done", 12.3, verdict="pass", findings_count=2)

        resp = client.get("/history")
        assert resp.status_code == 200
        rows = resp.json()
        assert [r["id"] for r in rows] == ["r1"]
        assert rows[0]["verdict"] == "pass"
        assert rows[0]["findings_count"] == 2

        resp = client.get("/history/r1")
        assert resp.status_code == 200
        assert resp.json()["scenario"] == "log in and check the cart"

        assert client.get("/history/nope").status_code == 404

        assert client.delete("/history/r1").status_code == 200
        assert client.get("/history/r1").status_code == 404


def test_health_reports_browser_status(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        # get_browser was stubbed to return None → is_connected() attribute error
        # path exercises the graceful-degradation branch.
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
