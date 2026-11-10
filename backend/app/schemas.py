"""Pydantic request/response schemas for the snippet API.

Validation boundaries (see docs/ARCHITECTURE.md §3):
- `title`: non-empty after trimming, max 200 chars.
- `language`: one of the 5 supported languages.
- `code`: non-empty after trimming, max 50,000 chars (~1.2-1.5k tokens of headroom under
  the local code model's context window; a single configurable cap, documented in README).

A failed constraint raises a Pydantic ValidationError, which FastAPI surfaces as HTTP 422
(reshaped into the `{error: {code, message}}` envelope by app.errors).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from .models import LANGUAGES

TITLE_MAX = 200
CODE_MAX = 50_000

# Derived dashboard status (docs/ARCHITECTURE.md §2) — computed, never stored.
DerivedStatus = Literal["not_reviewed", "in_progress", "reviewed", "failed"]


class SnippetCreate(BaseModel):
    """Request body for POST /api/snippets."""

    title: str
    language: str
    code: str

    @field_validator("language")
    @classmethod
    def _language_supported(cls, v: str) -> str:
        if v not in LANGUAGES:
            raise ValueError(f"language must be one of: {', '.join(LANGUAGES)}")
        return v

    @field_validator("title")
    @classmethod
    def _title_non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title must not be empty")
        if len(v) > TITLE_MAX:
            raise ValueError(f"title must be at most {TITLE_MAX} characters")
        return v

    @field_validator("code")
    @classmethod
    def _code_bounds(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("code must not be empty")
        if len(v) > CODE_MAX:
            raise ValueError(f"code must be at most {CODE_MAX} characters")
        return v


class SnippetRead(BaseModel):
    """Snippet response (list + detail). `status` is the derived dashboard status."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    language: str
    code: str
    created_at: datetime
    status: DerivedStatus


class FindingRead(BaseModel):
    """One finding in a completed review."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    line_start: int
    line_end: int
    severity: str
    category: str
    description: str
    rationale: str | None
    suggested_fix: str | None
    resolution_status: str
    resolution_reason: str | None
    resolved_at: datetime | None


class ReviewRead(BaseModel):
    """A review's current state. Provenance (provider/model/versions) reflects what actually
    ran this review, read from the stored row — never re-read from live settings. `findings`
    is populated on a completed review; `error_message` on a failed one."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    snippet_id: str
    run_number: int
    status: str
    provider: str | None
    model_name: str | None
    prompt_version: str | None
    rubric_version: str | None
    rejected_finding_count: int
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    findings: list[FindingRead] = []
