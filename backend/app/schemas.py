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
    """Snippet response (create + list row). `status` is the derived dashboard status;
    `reviewer` is the latest review's model (None if never reviewed); `finding_count` is the
    last successful review's finding count (0 if none)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    language: str
    code: str
    created_at: datetime
    status: DerivedStatus
    reviewer: str | None = None
    reviewer_provider: str | None = None  # so the UI can flag a mock (demo) reviewer
    finding_count: int = 0


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


RESOLUTION_REASON_MAX = 1000


class FindingResolutionUpdate(BaseModel):
    """PATCH body for resolving a finding. `resolution_reason` distinguishes three cases:
    omitted (field absent) preserves the existing reason on a same-status edit; explicit
    `null` clears it; a string replaces it. The handler reads `model_fields_set` to tell
    omitted from an explicit null. Whitespace-only reasons normalize to null."""

    resolution_status: Literal["open", "accepted", "dismissed"]
    resolution_reason: str | None = None

    @field_validator("resolution_reason")
    @classmethod
    def _normalize_reason(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if len(v) > RESOLUTION_REASON_MAX:
            raise ValueError(
                f"resolution_reason must be at most {RESOLUTION_REASON_MAX} characters"
            )
        return v


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


class ReviewSummary(BaseModel):
    """A review's state WITHOUT its findings — used in the snippet detail (E2) to describe
    the latest attempt and the run whose findings are being shown, separately."""

    model_config = ConfigDict(from_attributes=True)

    id: str
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


class SnippetDetail(BaseModel):
    """GET /api/snippets/{id} — the E2 shape. `latest_review` is the newest attempt (for the
    status header); `displayed_review` is the newest COMPLETED run whose `findings` we show.
    When they differ, the findings are historical and the UI must label them read-only."""

    id: str
    title: str
    language: str
    code: str
    created_at: datetime
    status: DerivedStatus
    latest_review: ReviewSummary | None
    displayed_review: ReviewSummary | None
    findings: list[FindingRead] = []


QUESTION_MAX = 2000


class DiscussRequest(BaseModel):
    """POST body for a finding discussion message."""

    question: str

    @field_validator("question")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be empty")
        if len(v) > QUESTION_MAX:
            raise ValueError(f"question must be at most {QUESTION_MAX} characters")
        return v


class MessageRead(BaseModel):
    """One message in a finding's discussion thread. `provider`/`model_name` are set on
    ASSISTANT messages (which model answered) and null on user messages."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    content: str
    provider: str | None
    model_name: str | None
    created_at: datetime


class RubricDimension(BaseModel):
    category: str
    description: str


class RubricSeverity(BaseModel):
    severity: str
    definition: str


class RubricResponse(BaseModel):
    """GET /api/rubric — the static, versioned rubric for the Review Details drawer."""

    name: str
    rubric_version: str
    prompt_version: str
    dimensions: list[RubricDimension]
    severities: list[RubricSeverity]
