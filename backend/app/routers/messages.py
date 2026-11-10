"""Finding discussion endpoints (M6).

- GET  /api/findings/{id}/messages  → the thread (allowed for any finding, incl. historical).
- POST /api/findings/{id}/messages  → ask a finding-grounded question. 404 if the finding is
  gone; 409 if it is historical (only the latest review's findings accept new questions);
  503 (retryable) if the model call fails — in which case NOTHING is persisted (no half
  thread). On success the user + assistant messages are saved ATOMICALLY in one transaction,
  and the assistant message records which provider/model actually answered.

The snippet code and the user's question are passed to the model as DATA, not instructions.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Finding, FindingMessage, Review, Snippet
from ..providers import ProviderError, get_provider
from ..schemas import DiscussRequest, MessageRead
from .findings import _is_latest_review

logger = logging.getLogger("app.discuss")
router = APIRouter(prefix="/api/findings", tags=["discussion"])


def _thread(db: Session, finding_id: str) -> list[FindingMessage]:
    return list(
        db.scalars(
            select(FindingMessage)
            .where(FindingMessage.finding_id == finding_id)
            .order_by(FindingMessage.created_at, FindingMessage.id)
        ).all()
    )


def _finding_context(finding: Finding) -> dict:
    return {
        "line_start": finding.line_start,
        "line_end": finding.line_end,
        "severity": finding.severity,
        "category": finding.category,
        "description": finding.description,
        "rationale": finding.rationale,
        "suggested_fix": finding.suggested_fix,
    }


@router.get("/{finding_id}/messages", response_model=list[MessageRead])
def list_messages(finding_id: str, db: Session = Depends(get_db)) -> list[FindingMessage]:
    if db.get(Finding, finding_id) is None:
        raise HTTPException(status_code=404, detail="finding not found")
    return _thread(db, finding_id)


@router.post("/{finding_id}/messages", response_model=list[MessageRead])
async def post_message(
    finding_id: str, payload: DiscussRequest, db: Session = Depends(get_db)
):
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="finding not found")

    review = db.get(Review, finding.review_id)
    if review is None or not _is_latest_review(db, review):
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "finding_read_only",
                    "message": "This finding belongs to a historical review and cannot be discussed.",
                    "review_id": finding.review_id,
                }
            },
        )

    snippet = db.get(Snippet, review.snippet_id)
    history = [{"role": m.role, "content": m.content} for m in _thread(db, finding_id)]

    provider = get_provider(settings)
    try:
        answer = await provider.discuss(
            code=snippet.code,
            language=snippet.language,
            finding=_finding_context(finding),
            history=history,
            question=payload.question,
        )
    except ProviderError as exc:
        # Save NOTHING — no half thread. The model may still be reachable later; this is a
        # status of the call, not of the review.
        logger.warning("discuss failed for finding %s: %s", finding_id, exc)
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "discuss_failed",
                    "message": "The discussion request could not be completed. Please retry.",
                }
            },
        )

    # The model call above was awaited WITHOUT a lock, so a new review may have been created
    # meanwhile — turning this finding historical. The entry check (line above) ran before the
    # call and cannot see that. Re-validate atomically before persisting (TOCTOU guard, D4):
    #   1. drop the pre-call read snapshot so the re-check sees the freshest committed state;
    #   2. flush the user row — this takes SQLite's single-writer lock, so from here no other
    #      writer (a competing enqueue) can commit until we commit or roll back;
    #   3. re-check that the finding is still on the latest review. If a newer review already
    #      committed, it is visible now → roll back (so NOTHING is saved) and return the same
    #      409 a historical finding gets. If not, the write lock guarantees any newer review
    #      can only commit AFTER ours, so persisting the pair here is a valid serialization.
    # A genuine persistence failure stays retryable (roll back, 503) rather than a bare 500.
    guard_review_id = finding.review_id
    try:
        db.rollback()
        db.add(FindingMessage(finding_id=finding_id, role="user", content=payload.question))
        db.flush()  # acquire the write lock before the re-check
        current = db.get(Review, guard_review_id)
        if current is None or not _is_latest_review(db, current):
            db.rollback()  # a newer review won the race — save nothing
            return JSONResponse(
                status_code=409,
                content={
                    "error": {
                        "code": "finding_read_only",
                        "message": "This finding belongs to a historical review and cannot be discussed.",
                        "review_id": guard_review_id,
                    }
                },
            )
        db.add(
            FindingMessage(
                finding_id=finding_id,
                role="assistant",
                content=answer,
                provider=provider.name,
                model_name=provider.model_name,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("persisting discussion for finding %s failed", finding_id)
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "discuss_failed",
                    "message": "The discussion reply could not be saved. Please retry.",
                }
            },
        )
    return _thread(db, finding_id)
