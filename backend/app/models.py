"""API request/response models for the AutoQA HTTP surface."""
from __future__ import annotations

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    url: str = Field(min_length=1)
    scenario: str = Field(min_length=1)
    max_steps: int | None = None


class ApprovalRequest(BaseModel):
    run_id: str
    approved: bool
    edited_args: dict | None = None


class RunSummary(BaseModel):
    id: str
    scenario: str
    url: str
    status: str
    created_at: str
    elapsed_s: float | None = None
    verdict: str | None = None
    findings_count: int | None = None


class RunEvent(BaseModel):
    event: str
    data: dict
    ts: str


class RunDetail(RunSummary):
    events: list[RunEvent] = []
