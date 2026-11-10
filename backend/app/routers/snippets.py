"""Snippet CRUD + dashboard/detail read models.

- POST /api/snippets      → 201, create an immutable snippet.
- GET  /api/snippets      → dashboard rows (derived status + reviewer + finding count).
- GET  /api/snippets/{id} → detail with the E2 shape: the latest review's status separate
  from the last SUCCESSFUL run's findings, so the UI can label historical findings.

Each response carries the DERIVED dashboard status (from the snippet's latest review by
run_number). `reviewer` is the latest review's model; `finding_count` / the displayed
findings come from the newest COMPLETED review (the "last successful" rule, E2).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Finding, Review, Snippet
from ..schemas import (
    DerivedStatus,
    ReviewSummary,
    SnippetCreate,
    SnippetDetail,
    SnippetRead,
)

router = APIRouter(prefix="/api/snippets", tags=["snippets"])

_STATUS_MAP: dict[str, DerivedStatus] = {
    "queued": "in_progress",
    "running": "in_progress",
    "completed": "reviewed",
    "failed": "failed",
}


def _latest_review(db: Session, snippet_id: str) -> Review | None:
    return db.scalar(
        select(Review)
        .where(Review.snippet_id == snippet_id)
        .order_by(Review.run_number.desc())
        .limit(1)
    )


def _last_successful_review(db: Session, snippet_id: str) -> Review | None:
    return db.scalar(
        select(Review)
        .where(Review.snippet_id == snippet_id, Review.status == "completed")
        .order_by(Review.run_number.desc())
        .limit(1)
    )


def _derive_status(latest: Review | None) -> DerivedStatus:
    if latest is None:
        return "not_reviewed"
    return _STATUS_MAP.get(latest.status, "not_reviewed")


def _finding_count(db: Session, review: Review | None) -> int:
    if review is None:
        return 0
    return db.scalar(
        select(func.count(Finding.id)).where(Finding.review_id == review.id)
    ) or 0


def _summary(db: Session, snippet: Snippet) -> SnippetRead:
    latest = _latest_review(db, snippet.id)
    successful = _last_successful_review(db, snippet.id)
    return SnippetRead(
        id=snippet.id,
        title=snippet.title,
        language=snippet.language,
        code=snippet.code,
        created_at=snippet.created_at,
        status=_derive_status(latest),
        reviewer=latest.model_name if latest else None,
        finding_count=_finding_count(db, successful),
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SnippetRead)
def create_snippet(payload: SnippetCreate, db: Session = Depends(get_db)) -> SnippetRead:
    snippet = Snippet(
        title=payload.title, language=payload.language, code=payload.code
    )
    db.add(snippet)
    db.commit()
    db.refresh(snippet)
    return _summary(db, snippet)


@router.get("", response_model=list[SnippetRead])
def list_snippets(db: Session = Depends(get_db)) -> list[SnippetRead]:
    snippets = db.scalars(
        select(Snippet).order_by(Snippet.created_at.desc())
    ).all()
    return [_summary(db, s) for s in snippets]


@router.get("/{snippet_id}", response_model=SnippetDetail)
def get_snippet(snippet_id: str, db: Session = Depends(get_db)) -> SnippetDetail:
    snippet = db.get(Snippet, snippet_id)
    if snippet is None:
        raise HTTPException(status_code=404, detail="snippet not found")

    latest = _latest_review(db, snippet.id)
    displayed = _last_successful_review(db, snippet.id)
    findings = []
    if displayed is not None:
        displayed.findings.sort(key=lambda f: (f.line_start, f.line_end, f.id))
        findings = list(displayed.findings)

    return SnippetDetail(
        id=snippet.id,
        title=snippet.title,
        language=snippet.language,
        code=snippet.code,
        created_at=snippet.created_at,
        status=_derive_status(latest),
        latest_review=ReviewSummary.model_validate(latest) if latest else None,
        displayed_review=ReviewSummary.model_validate(displayed) if displayed else None,
        findings=findings,
    )
