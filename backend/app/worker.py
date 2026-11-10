"""In-process async review worker + enqueue + startup recovery (M3).

Design (single process, single worker — see the assumption note below):
- Enqueue inserts a `queued` review with a concurrency-safe run_number (the DB's unique +
  partial indexes arbitrate; we translate a lost race into a 409 or a bounded retry, never
  a 500). Provenance (provider/model/prompt/rubric versions) is stamped here, from the
  provider that will actually run it — the GET reads those stored columns, never live
  settings.
- One background loop claims the oldest queued review (an atomic conditional UPDATE
  queued→running), calls the provider (async, timeout-bounded), validates (pure), then
  commits findings + the terminal status in ONE transaction. The review is only `completed`
  after that commit succeeds — a model response is not a finished review until persisted.
- If the completion transaction fails while the process is alive, we roll back and, in a
  FRESH session, mark the review `failed` with a sanitized message — it never stays stuck
  in `running`. Only a genuinely unavailable DB falls through to restart recovery.
- On startup, any review left `running` by a crash is marked `failed`; `queued` reviews are
  preserved and picked up.

SINGLE-PROCESS ASSUMPTION: this worker and its startup recovery assume exactly one process.
Running multiple uvicorn workers would (a) run multiple competing loops and (b) make each
process's startup recovery mark the OTHER processes' in-flight `running` reviews as failed.
Deploy with a single worker process (the MVP target). A durable queue would be the
production answer.

All DB access here goes through `_session_scope` (patchable in tests) and runs off the event
loop via `asyncio.to_thread`, so a new SQLAlchemy Session is created per thread — Sessions
are never shared across threads.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from .config import settings
from .db import session_scope as _session_scope
from .models import Finding, Review, Snippet
from .providers import ProviderError, get_provider
from .review_pipeline import ValidatedReview, validate_review_output
from .rubric import PROMPT_VERSION, RUBRIC_VERSION

logger = logging.getLogger("app.worker")

POLL_INTERVAL = 0.3  # seconds to wait when no queued work
ENQUEUE_RETRIES = 5
_ACTIVE = ("queued", "running")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Enqueue (runs inside a request's Session) ----------------------------------


def _active_review(db: Session, snippet_id: str) -> Review | None:
    return db.scalar(
        select(Review)
        .where(Review.snippet_id == snippet_id, Review.status.in_(_ACTIVE))
        .limit(1)
    )


def enqueue_review(db: Session, snippet_id: str) -> tuple[Review | None, Review | None]:
    """Insert a queued review for a snippet. Returns (created, active_conflict):
    exactly one is non-None. An existing active review -> (None, that review) -> 409.

    Concurrency-safe without external locks: we compute run_number = MAX+1 and insert; if a
    concurrent writer beat us, the partial unique index (one active per snippet) or the
    UNIQUE(snippet_id, run_number) raises IntegrityError, which we translate — re-check for
    an active review (→ 409) or retry the allocation. busy_timeout makes writers wait rather
    than fail, so this converges to a 202 or a 409, never an unexpected 500.
    """
    provider = get_provider(settings)  # for provenance; also validates provider config
    for _ in range(ENQUEUE_RETRIES):
        active = _active_review(db, snippet_id)
        if active is not None:
            return None, active
        next_run = (
            db.scalar(
                select(func.max(Review.run_number)).where(
                    Review.snippet_id == snippet_id
                )
            )
            or 0
        ) + 1
        review = Review(
            snippet_id=snippet_id,
            run_number=next_run,
            status="queued",
            provider=provider.name,
            model_name=provider.model_name,
            prompt_version=PROMPT_VERSION,
            rubric_version=RUBRIC_VERSION,
        )
        db.add(review)
        try:
            db.commit()
            db.refresh(review)
            return review, None
        except (IntegrityError, OperationalError):
            db.rollback()
            active = _active_review(db, snippet_id)
            if active is not None:
                return None, active
            # run_number race with another snippet-less conflict: retry allocation.
    # Extremely unlikely after retries; surfaced as a controlled error by the caller.
    raise RuntimeError("could not allocate a review slot after retries")


# --- Claim + recovery (own Session via _session_scope) --------------------------


def claim_next_queued() -> str | None:
    """Atomically claim the oldest queued review (queued→running) and return its id."""
    with _session_scope() as db:
        review_id = db.scalar(
            select(Review.id)
            .where(Review.status == "queued")
            .order_by(Review.created_at, Review.run_number)
            .limit(1)
        )
        if review_id is None:
            return None
        # Conditional update: only transition if still queued (atomic claim).
        result = db.execute(
            update(Review)
            .where(Review.id == review_id, Review.status == "queued")
            .values(status="running", started_at=_utcnow())
        )
        if result.rowcount != 1:
            return None  # someone else claimed it (shouldn't happen with one worker)
        return review_id


def recover_interrupted_reviews() -> int:
    """Startup recovery: mark any `running` review (crashed mid-run) as failed; leave
    `queued` reviews for the worker. Returns how many were recovered."""
    with _session_scope() as db:
        result = db.execute(
            update(Review)
            .where(Review.status == "running")
            .values(
                status="failed",
                error_message="Review was interrupted by a server restart.",
                completed_at=_utcnow(),
            )
        )
        return result.rowcount


# --- Processing a claimed review ------------------------------------------------


def _load_review_input(review_id: str) -> tuple[str, str, int] | None:
    """Return (code, language, line_count) for a review's snippet, or None if gone."""
    with _session_scope() as db:
        review = db.get(Review, review_id)
        if review is None:
            return None
        snippet = db.get(Snippet, review.snippet_id)
        if snippet is None:
            return None
        return snippet.code, snippet.language, len(snippet.code.splitlines())


_SAFE_ERROR = {
    "invalid_response": "The model's output could not be parsed as valid findings.",
    "validation_error": "The model returned findings but none passed validation.",
    "provider_error": "The review could not be completed (the model call failed).",
}


def _safe_error(result: ValidatedReview) -> str:
    return _SAFE_ERROR.get(result.error_code or "", "The review failed.")


def _apply_result(db: Session, review: Review, result: ValidatedReview) -> None:
    """Write the terminal outcome onto an in-progress review (findings + status), all within
    the caller's transaction. Separated out so a test can inject a persistence failure."""
    if result.status == "completed":
        for f in result.findings:
            db.add(
                Finding(
                    review_id=review.id,
                    line_start=f["line_start"],
                    line_end=f["line_end"],
                    severity=f["severity"],
                    category=f["category"],
                    description=f["description"],
                    rationale=f["rationale"],
                    suggested_fix=f["suggested_fix"],
                )
            )
        review.status = "completed"
        review.rejected_finding_count = result.rejected_count
        review.completed_at = _utcnow()
    else:
        review.status = "failed"
        review.error_message = _safe_error(result)
        review.completed_at = _utcnow()


def _persist_result(review_id: str, result: ValidatedReview) -> None:
    """Commit the review outcome atomically. If the transaction fails while the DB is still
    reachable, mark the review failed in a fresh session so it never stays stuck running."""
    try:
        with _session_scope() as db:
            review = db.get(Review, review_id)
            if review is None:
                return
            _apply_result(db, review, result)
    except Exception:
        logger.exception("persisting review %s failed; marking it failed", review_id)
        _mark_failed_fresh(review_id, "The review results could not be saved.")


def _mark_failed_fresh(review_id: str, message: str) -> None:
    """Best-effort: in a brand-new transaction, flip an unfinished review to failed. If the
    DB is genuinely unavailable this also fails — then restart recovery is the backstop."""
    try:
        with _session_scope() as db:
            review = db.get(Review, review_id)
            if review is not None and review.status not in ("completed", "failed"):
                review.status = "failed"
                review.error_message = message
                review.completed_at = _utcnow()
    except Exception:
        logger.exception(
            "could not mark review %s failed; leaving for restart recovery", review_id
        )


async def process_claimed(review_id: str) -> None:
    """Run the provider for an already-claimed (running) review and persist the outcome.

    The review is `running` on entry, so this MUST drive it to a terminal state no matter
    what. ProviderError becomes a clean failed result; any OTHER unexpected error (a broken
    provider config, an HTTP error the provider didn't wrap, a DB error while loading) is
    caught here and the review is marked failed in a fresh session. A claimed review can
    therefore never stay stuck in `running` and lock its snippet behind a 409.
    """
    try:
        data = await asyncio.to_thread(_load_review_input, review_id)
        if data is None:
            return
        code, language, line_count = data

        provider = get_provider(settings)
        try:
            raw = await provider.review(code=code, language=language)
            result = validate_review_output(raw, line_count)
        except ProviderError as exc:
            logger.warning("provider error on review %s: %s", review_id, exc)
            result = ValidatedReview(
                status="failed", error_code="provider_error", error_message=str(exc)
            )

        await asyncio.to_thread(_persist_result, review_id, result)
    except Exception:
        # Safety net: anything unexpected after the claim must not leave the row running.
        logger.exception("unexpected error processing review %s", review_id)
        await asyncio.to_thread(
            _mark_failed_fresh, review_id, "The review failed unexpectedly."
        )


# --- The loop -------------------------------------------------------------------


async def process_next() -> bool:
    """One loop iteration: claim + process the next queued review. Returns True if it did
    work, False if the queue was empty. Deterministic — tests drive it directly."""
    review_id = await asyncio.to_thread(claim_next_queued)
    if review_id is None:
        return False
    await process_claimed(review_id)
    return True


async def worker_loop(stop_event: asyncio.Event) -> None:
    """Run until stop_event is set: process queued reviews, sleep when idle."""
    logger.info("review worker started")
    while not stop_event.is_set():
        try:
            did_work = await process_next()
        except Exception:
            logger.exception("worker iteration failed")
            did_work = False
        if not did_work:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=POLL_INTERVAL)
            except asyncio.TimeoutError:
                pass
    logger.info("review worker stopped")
