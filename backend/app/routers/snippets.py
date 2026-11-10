"""Snippet CRUD endpoints (M1).

- POST /api/snippets      → 201, create an immutable snippet.
- GET  /api/snippets      → list, newest first, each with derived status.
- GET  /api/snippets/{id} → one snippet, or 404.

Review/finding endpoints are added in later milestones. Each response carries the DERIVED
dashboard status (computed from the snippet's latest review by run_number); with no reviews
yet it is always `not_reviewed`, and the logic is correct once reviews land in M3.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Review, Snippet
from ..schemas import DerivedStatus, SnippetCreate, SnippetRead

router = APIRouter(prefix="/api/snippets", tags=["snippets"])

# Latest review status → derived dashboard status (docs/ARCHITECTURE.md §2).
_STATUS_MAP: dict[str, DerivedStatus] = {
    "queued": "in_progress",
    "running": "in_progress",
    "completed": "reviewed",
    "failed": "failed",
}


def _derive_status(db: Session, snippet_id: str) -> DerivedStatus:
    """Dashboard status from the snippet's latest review (highest run_number)."""
    latest = db.scalar(
        select(Review.status)
        .where(Review.snippet_id == snippet_id)
        .order_by(Review.run_number.desc())
        .limit(1)
    )
    if latest is None:
        return "not_reviewed"
    return _STATUS_MAP.get(latest, "not_reviewed")


def _to_read(db: Session, snippet: Snippet) -> SnippetRead:
    return SnippetRead(
        id=snippet.id,
        title=snippet.title,
        language=snippet.language,
        code=snippet.code,
        created_at=snippet.created_at,
        status=_derive_status(db, snippet.id),
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SnippetRead)
def create_snippet(payload: SnippetCreate, db: Session = Depends(get_db)) -> SnippetRead:
    snippet = Snippet(
        title=payload.title, language=payload.language, code=payload.code
    )
    db.add(snippet)
    db.commit()
    db.refresh(snippet)
    return _to_read(db, snippet)


@router.get("", response_model=list[SnippetRead])
def list_snippets(db: Session = Depends(get_db)) -> list[SnippetRead]:
    snippets = db.scalars(
        select(Snippet).order_by(Snippet.created_at.desc())
    ).all()
    return [_to_read(db, s) for s in snippets]


@router.get("/{snippet_id}", response_model=SnippetRead)
def get_snippet(snippet_id: str, db: Session = Depends(get_db)) -> SnippetRead:
    snippet = db.get(Snippet, snippet_id)
    if snippet is None:
        raise HTTPException(status_code=404, detail="snippet not found")
    return _to_read(db, snippet)
