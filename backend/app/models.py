"""SQLAlchemy 2.0 ORM models — the 4 tables of the Code Snippet Reviewer.

Design notes (see docs/ARCHITECTURE.md §2, docs/DECISIONS.md):
- Enums are enforced as SQLite CHECK constraints, not Python-only Enum types, so the
  database itself rejects an out-of-range value even if application validation is bypassed.
- `snippets` is immutable after creation (no `updated_at`): a finding's line range always
  refers to the exact code it was generated against, never to shifted lines.
- At most ONE active review per snippet is enforced atomically by a PARTIAL UNIQUE INDEX
  (`ux_one_active_review`) — a DB-level guard, not an application check, so two concurrent
  enqueue attempts can never both win. `run_number` is additionally unique per snippet.
- Timestamps are timezone-aware UTC, set in Python on insert.

Table creation is via `Base.metadata.create_all()` on startup (MVP). This does NOT migrate
an existing schema — a production deployment would use Alembic (see README).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# Supported snippet languages (docs/DECISIONS.md §Languages).
LANGUAGES = ("python", "javascript", "typescript", "java", "go")

# Enum value sets, enforced as DB CHECK constraints below.
REVIEW_STATUSES = ("queued", "running", "completed", "failed")
SEVERITIES = ("critical", "warning", "info")
CATEGORIES = ("bug", "security", "performance", "maintainability")
RESOLUTION_STATUSES = ("open", "accepted", "dismissed")
MESSAGE_ROLES = ("user", "assistant")


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _in_set_sql(column: str, values: tuple[str, ...]) -> str:
    """Render `column IN ('a','b',...)` for a CHECK constraint."""
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


class Snippet(Base):
    """A submitted code snippet. Immutable after creation."""

    __tablename__ = "snippets"
    __table_args__ = (
        CheckConstraint(_in_set_sql("language", LANGUAGES), name="ck_snippet_language"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)

    reviews: Mapped[list["Review"]] = relationship(
        back_populates="snippet",
        cascade="all, delete-orphan",
        order_by="Review.run_number",
    )


class Review(Base):
    """One review run over a snippet. At most one active (queued/running) per snippet."""

    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint(_in_set_sql("status", REVIEW_STATUSES), name="ck_review_status"),
        # One run_number per snippet (stable "latest" key; atomic allocation is M3).
        UniqueConstraint("snippet_id", "run_number", name="uq_review_snippet_run"),
        # At most one ACTIVE review per snippet — partial unique index (SQLite WHERE).
        Index(
            "ux_one_active_review",
            "snippet_id",
            unique=True,
            sqlite_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    snippet_id: Mapped[str] = mapped_column(
        ForeignKey("snippets.id", ondelete="CASCADE"), nullable=False
    )
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Provenance: which model actually generated this run.
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String, nullable=True)
    rubric_version: Mapped[str | None] = mapped_column(String, nullable=True)
    rejected_finding_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    snippet: Mapped["Snippet"] = relationship(back_populates="reviews")
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )


class Finding(Base):
    """A single issue found in a review. Resolutions are scoped to this review run."""

    __tablename__ = "findings"
    __table_args__ = (
        CheckConstraint("line_start >= 1", name="ck_finding_line_start"),
        CheckConstraint("line_end >= line_start", name="ck_finding_line_end"),
        CheckConstraint(_in_set_sql("severity", SEVERITIES), name="ck_finding_severity"),
        CheckConstraint(_in_set_sql("category", CATEGORIES), name="ck_finding_category"),
        CheckConstraint(
            _in_set_sql("resolution_status", RESOLUTION_STATUSES),
            name="ck_finding_resolution_status",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    review_id: Mapped[str] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False
    )
    line_start: Mapped[int] = mapped_column(Integer, nullable=False)
    line_end: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_fix: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_status: Mapped[str] = mapped_column(
        String, nullable=False, default="open"
    )
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)

    review: Mapped["Review"] = relationship(back_populates="findings")
    messages: Mapped[list["FindingMessage"]] = relationship(
        back_populates="finding", cascade="all, delete-orphan"
    )


class FindingMessage(Base):
    """One message in a finding's Discuss thread (user question / assistant answer)."""

    __tablename__ = "finding_messages"
    __table_args__ = (
        CheckConstraint(_in_set_sql("role", MESSAGE_ROLES), name="ck_message_role"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    finding_id: Mapped[str] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Provenance of an ASSISTANT message — which model actually answered. NULL on user
    # messages. Lets the UI show "answered by X" and never imply the review model and the
    # discuss model are the same when they differ.
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)

    finding: Mapped["Finding"] = relationship(back_populates="messages")
