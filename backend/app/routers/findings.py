"""Finding resolution endpoint (M4).

PATCH /api/findings/{id} records a HUMAN decision on an AI finding: accept the suggestion,
dismiss it, or reopen it, with an optional reason. These are user decisions, NOT verified
true/false-positive labels.

Rules (agreed with the product owner):
- resolved_at marks when the finding became (or switched between) accepted/dismissed. It is
  refreshed only when the resolution STATUS changes into accepted/dismissed — editing the
  reason alone never moves it. Reopening (-> open) clears both the reason and resolved_at.
- resolution_reason: omitted (absent from the body) preserves the current reason on a
  same-status edit; explicit null clears it; a string replaces it. A status change with no
  reason clears the old one (so a dismiss reason never carries into an accept).
- Identical repeat requests are idempotent: nothing persisted changes, timestamps included.
- Historical read-only: only findings of a snippet's LATEST review (highest run_number) may
  be modified. Findings from earlier runs stay viewable but PATCH returns 409 — enforced in
  the backend, not just the UI.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Finding, Review
from ..schemas import FindingRead, FindingResolutionUpdate

router = APIRouter(prefix="/api", tags=["findings"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_latest_review(db: Session, review: Review) -> bool:
    latest_id = db.scalar(
        select(Review.id)
        .where(Review.snippet_id == review.snippet_id)
        .order_by(Review.run_number.desc())
        .limit(1)
    )
    return latest_id == review.id


@router.patch("/findings/{finding_id}", response_model=FindingRead)
def resolve_finding(
    finding_id: str,
    payload: FindingResolutionUpdate,
    db: Session = Depends(get_db),
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
                    "message": "This finding belongs to a historical review and cannot be modified.",
                    "review_id": finding.review_id,
                }
            },
        )

    new_status = payload.resolution_status
    reason_provided = "resolution_reason" in payload.model_fields_set
    current_status = finding.resolution_status
    status_changed = new_status != current_status

    # Resolve the new reason.
    if new_status == "open":
        new_reason = None
    elif reason_provided:
        new_reason = payload.resolution_reason  # already normalized (str or None)
    elif status_changed:
        new_reason = None  # don't carry a prior resolution's reason into a new decision
    else:
        new_reason = finding.resolution_reason  # same status, omitted -> preserve

    # Resolve resolved_at.
    if new_status == "open":
        new_resolved_at = None
    elif status_changed:
        new_resolved_at = _utcnow()  # became / switched to a resolved state
    else:
        new_resolved_at = finding.resolved_at  # reason edit alone -> unchanged

    # Idempotent: if nothing persisted would change, don't write (keeps timestamps stable).
    if new_status == current_status and new_reason == finding.resolution_reason:
        return finding

    finding.resolution_status = new_status
    finding.resolution_reason = new_reason
    finding.resolved_at = new_resolved_at
    db.commit()
    db.refresh(finding)
    return finding
