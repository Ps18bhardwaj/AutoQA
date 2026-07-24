"""Unit tests for AutoQA Enterprise AI Quality Engines and REST endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.engines.rca_engine import RCAEngine
from app.engines.self_healing_engine import SelfHealingEngine
from app.engines.visual_regression_engine import VisualRegressionEngine
from app.engines.ux_evaluator import UXEvaluator
from app.engines.patch_generator import PatchGenerator
from app.engines.release_readiness_engine import ReleaseReadinessEngine
from app.engines.coverage_engine import CoverageEngine
from app.engines.knowledge_graph_engine import KnowledgeGraphEngine
from app.engines.report_exporter import ReportExporter

client = TestClient(app)


def test_rca_engine_analysis():
    rca = RCAEngine.analyze_finding(
        finding_type="console",
        title="Uncaught TypeError: Cannot read property 'id' of null",
        description="TypeError in client event handler",
        console_logs=[{"type": "error", "text": "Uncaught TypeError: Cannot read property 'id' of null"}],
    )
    assert rca.finding_id.startswith("rca_")
    assert rca.confidence_score >= 0.8
    assert "TypeError" in rca.root_cause_explanation
    assert rca.suggested_patch != ""


def test_self_healing_engine():
    candidate = SelfHealingEngine.attempt_recovery(
        failed_selector="#submit-button-id",
        target_role="button",
        target_name="Submit",
    )
    assert candidate.recovered is True
    assert "button" in candidate.healed_selector
    assert candidate.confidence > 0.9


def test_ux_evaluator():
    result = UXEvaluator.evaluate_page_ux(
        aria_snapshot_text="heading 'Login'\nbutton 'Sign In'\ntextbox 'Username'",
        findings_count=0,
    )
    assert result.overall_ux_score > 80.0
    assert len(result.metrics) >= 3


def test_release_readiness_engine():
    report = ReleaseReadinessEngine.calculate_readiness(
        project_id="test_proj",
        build_version="v3.0.0",
        verdict="pass",
        findings_count=0,
    )
    assert report.ship_recommendation == "SHIP_READY"
    assert report.overall_readiness_score > 90.0


def test_enterprise_api_endpoints():
    # Test RCA endpoint
    resp_rca = client.post("/api/v1/rca/analyze", json={
        "type": "a11y",
        "title": "Color contrast violation",
        "description": "Text contrast ratio below 4.5:1",
    })
    assert resp_rca.status_code == 200
    assert "rca" in resp_rca.json()
    assert "patch" in resp_rca.json()

    # Test Self Healing endpoint
    resp_heal = client.post("/api/v1/self-healing/heal", json={
        "failed_selector": "button.checkout",
        "target_role": "button",
        "target_name": "Checkout",
    })
    assert resp_heal.status_code == 200
    assert resp_heal.json()["recovered"] is True

    # Test Knowledge Graph endpoint
    resp_graph = client.get("/api/v1/knowledge-graph?project_id=default")
    assert resp_graph.status_code == 200
    assert len(resp_graph.json()["nodes"]) > 0

    # Test Release Readiness endpoint
    resp_ready = client.get("/api/v1/release-readiness?project_id=default&verdict=pass")
    assert resp_ready.status_code == 200
    assert resp_ready.json()["overall_readiness_score"] >= 80.0

    # Test Report Exporter endpoint
    resp_report = client.post("/api/v1/reports/export", json={
        "run_id": "test_run_123",
        "url": "http://localhost:5173",
        "scenario": "Login and Verify Dashboard",
        "verdict": "pass",
        "release_score": 96.5,
        "findings": [],
    })
    assert resp_report.status_code == 200
    assert "# Executive Quality & Release Audit Report" in resp_report.json()["markdown"]
