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
    ReviewRunRead,
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


def _review_count(db: Session, snippet_id: str) -> int:
    return db.scalar(
        select(func.count(Review.id)).where(Review.snippet_id == snippet_id)
    ) or 0


def _summary(db: Session, snippet: Snippet, review_count: int | None = None) -> SnippetRead:
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
        reviewer_provider=latest.provider if latest else None,
        finding_count=_finding_count(db, successful),
        # Caller may pass a precomputed count (list view batches it in ONE query); for a single
        # snippet we count directly. Either way it is NOT an extra per-row query in the list.
        review_count=_review_count(db, snippet.id) if review_count is None else review_count,
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
    # Batch the per-snippet review-run count into ONE aggregate query (no extra query per row).
    counts: dict[str, int] = dict(
        db.execute(
            select(Review.snippet_id, func.count(Review.id)).group_by(Review.snippet_id)
        ).all()
    )
    return [_summary(db, s, review_count=counts.get(s.id, 0)) for s in snippets]


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


@router.get("/{snippet_id}/reviews", response_model=list[ReviewRunRead])
def list_snippet_reviews(snippet_id: str, db: Session = Depends(get_db)) -> list[ReviewRunRead]:
    """Read-only run history for a snippet: every review run (queued/running/completed/failed),
    newest first, each with its finding count. Powers the run selector — it only LISTS runs; the
    read-only rule for modifying a historical run's findings/discussion is enforced where those
    writes happen (PATCH /findings, POST /findings/{id}/messages), not here."""
    if db.get(Snippet, snippet_id) is None:
        raise HTTPException(status_code=404, detail="snippet not found")

    reviews = db.scalars(
        select(Review)
        .where(Review.snippet_id == snippet_id)
        .order_by(Review.run_number.desc())
    ).all()
    # Finding counts for all of this snippet's runs in ONE aggregate query (no per-run query).
    counts: dict[str, int] = dict(
        db.execute(
            select(Finding.review_id, func.count(Finding.id))
            .where(Finding.review_id.in_([r.id for r in reviews]))
            .group_by(Finding.review_id)
        ).all()
    ) if reviews else {}

    return [
        ReviewRunRead(
            id=r.id,
            run_number=r.run_number,
            status=r.status,
            provider=r.provider,
            model_name=r.model_name,
            error_message=r.error_message,
            created_at=r.created_at,
            completed_at=r.completed_at,
            finding_count=counts.get(r.id, 0),
        )
        for r in reviews
    ]
