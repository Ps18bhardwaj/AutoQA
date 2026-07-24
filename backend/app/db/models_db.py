"""Database ORM models for AutoQA Enterprise Quality Engineering Platform."""
from __future__ import annotations

from datetime import datetime
import json
from typing import Any, Dict, List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class ProjectDB(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    runs: Mapped[List["RunDB"]] = relationship("RunDB", back_populates="project", cascade="all, delete-orphan")


class RunDB(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("projects.id"), nullable=True)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    scenario: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="running")  # running, completed, failed, paused
    verdict: Mapped[str] = mapped_column(String(32), default="pending")  # pass, fail, blocked
    
    # Quality Scores
    release_score: Mapped[float] = mapped_column(Float, default=95.0)
    ux_score: Mapped[float] = mapped_column(Float, default=90.0)
    perf_score: Mapped[float] = mapped_column(Float, default=88.0)
    sec_score: Mapped[float] = mapped_column(Float, default=96.0)
    a11y_score: Mapped[float] = mapped_column(Float, default=92.0)
    
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    project: Mapped[Optional["ProjectDB"]] = relationship("ProjectDB", back_populates="runs")
    steps: Mapped[List["RunStepDB"]] = relationship("RunStepDB", back_populates="run", cascade="all, delete-orphan")
    findings: Mapped[List["FindingRCADB"]] = relationship("FindingRCADB", back_populates="run", cascade="all, delete-orphan")
    visual_regressions: Mapped[List["VisualRegressionDB"]] = relationship("VisualRegressionDB", back_populates="run", cascade="all, delete-orphan")


class RunStepDB(Base):
    __tablename__ = "run_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id"), nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    action_payload: Mapped[str] = mapped_column(Text, default="{}")
    screenshot_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    aria_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    thinking_trace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    run: Mapped["RunDB"] = relationship("RunDB", back_populates="steps")


class FindingRCADB(Base):
    __tablename__ = "findings_rca"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id"), nullable=False)
    finding_type: Mapped[str] = mapped_column(String(64), nullable=False)  # functional, a11y, console, network, visual
    severity: Mapped[str] = mapped_column(String(32), nullable=False)  # critical, major, minor, info
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Text] = mapped_column(Text, nullable=False)
    root_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.95)
    evidence_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    patch_diff: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_fix: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    run: Mapped["RunDB"] = relationship("RunDB", back_populates="findings")


class VisualRegressionDB(Base):
    __tablename__ = "visual_regressions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id"), nullable=False)
    element_selector: Mapped[str] = mapped_column(String(512), nullable=False)
    shift_type: Mapped[str] = mapped_column(String(64), nullable=False)  # layout_shift, color_mismatch, text_overflow, broken_spacing
    baseline_img: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    current_img: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    diff_description: Mapped[str] = mapped_column(Text, nullable=False)
    impact_score: Mapped[float] = mapped_column(Float, default=0.85)

    run: Mapped["RunDB"] = relationship("RunDB", back_populates="visual_regressions")


class RequirementCoverageDB(Base):
    __tablename__ = "requirement_coverage"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    requirement_text: Mapped[str] = mapped_column(Text, nullable=False)
    mapped_scenario: Mapped[str] = mapped_column(Text, nullable=False)
    coverage_percentage: Mapped[float] = mapped_column(Float, default=100.0)
    risk_level: Mapped[str] = mapped_column(String(32), default="low")
    test_cases_json: Mapped[str] = mapped_column(Text, default="[]")


class KnowledgeNodeDB(Base):
    __tablename__ = "quality_knowledge_nodes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    node_type: Mapped[str] = mapped_column(String(64), nullable=False)  # page, component, api, bug, run, developer
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class KnowledgeEdgeDB(Base):
    __tablename__ = "quality_knowledge_edges"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)  # calls_api, contains_bug, covers_page, fixed_by
