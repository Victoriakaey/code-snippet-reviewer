"""Review endpoints (M3): trigger a review and poll its state.

- POST /api/snippets/{id}/reviews -> 202 + the queued review. 404 if the snippet is gone.
  409 (with the active review's id, inside the error envelope) if one is already in flight.
- GET  /api/reviews/{id} -> the review's current state, with findings when completed and a
  sanitized error when failed.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Review, Snippet
from ..schemas import ReviewRead
from ..worker import enqueue_review

router = APIRouter(prefix="/api", tags=["reviews"])


@router.post("/snippets/{snippet_id}/reviews", status_code=status.HTTP_202_ACCEPTED,
             response_model=ReviewRead)
def create_review(snippet_id: str, db: Session = Depends(get_db)):
    if db.get(Snippet, snippet_id) is None:
        raise HTTPException(status_code=404, detail="snippet not found")

    try:
        created, active = enqueue_review(db, snippet_id)
    except RuntimeError:
        raise HTTPException(
            status_code=503, detail="could not enqueue review, please retry"
        )

    if active is not None:
        # Backward-compatible envelope extension: include the active review id so the client
        # can jump straight to the in-flight review instead of just showing an error.
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "review_already_active",
                    "message": "A review is already in progress for this snippet.",
                    "review_id": active.id,
                }
            },
        )
    return created


@router.get("/reviews/{review_id}", response_model=ReviewRead)
def get_review(review_id: str, db: Session = Depends(get_db)) -> Review:
    review = db.get(Review, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    # Deterministic finding order for the UI.
    review.findings.sort(key=lambda f: (f.line_start, f.line_end, f.id))
    return review
