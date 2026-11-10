"""Worker tests: claim, end-to-end processing, the four persisted outcomes, the
persistence-failure fallback, startup recovery, concurrent enqueue, and run isolation.

`worker_scope` (conftest) points the worker's own transaction scope at the test DB. Provider
behaviour is injected via a FakeProvider so outcomes are deterministic; one test uses the
real MockProvider through the factory to prove that path too.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

from app import worker
from app.config import settings
from app.models import Review, Snippet
from app.providers import ProviderError
from app.review_pipeline import ValidatedReview


class FakeProvider:
    name = "fake"
    model_name = "fake-1"

    def __init__(self, raw: str | None = None, error: str | None = None):
        self._raw = raw
        self._error = error

    async def review(self, *, code: str, language: str) -> str:
        if self._error is not None:
            raise ProviderError(self._error)
        assert self._raw is not None
        return self._raw


def _use_provider(monkeypatch, provider) -> None:
    monkeypatch.setattr(worker, "get_provider", lambda _s=None: provider)


def _seed_snippet(worker_scope, code: str = "password = 'x'\nprint(password)\n") -> str:
    with worker_scope() as db:
        snip = Snippet(title="t", language="python", code=code)
        db.add(snip)
        db.flush()
        return snip.id


def _enqueue(worker_scope, snippet_id: str) -> str:
    with worker_scope() as db:
        created, active = worker.enqueue_review(db, snippet_id)
        assert created is not None and active is None
        return created.id


def _valid_finding() -> dict:
    return {
        "line_start": 1,
        "line_end": 1,
        "severity": "warning",
        "category": "security",
        "description": "hardcoded secret",
        "rationale": "a committed secret leaks via version control",
        "suggested_fix": "use an env var",
    }


# --- Claim ----------------------------------------------------------------------


def test_claim_transitions_queued_to_running(worker_scope):
    sid = _seed_snippet(worker_scope)
    rid = _enqueue(worker_scope, sid)
    claimed = worker.claim_next_queued()
    assert claimed == rid
    with worker_scope() as db:
        r = db.get(Review, rid)
        assert r.status == "running"
        assert r.started_at is not None


def test_claim_returns_none_when_empty(worker_scope):
    assert worker.claim_next_queued() is None


# --- End-to-end through the real factory + MockProvider -------------------------


def test_process_next_completes_with_real_mock(worker_scope, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "mock")
    sid = _seed_snippet(worker_scope)
    rid = _enqueue(worker_scope, sid)

    assert asyncio.run(worker.process_next()) is True

    with worker_scope() as db:
        r = db.get(Review, rid)
        assert r.status == "completed"
        assert r.started_at is not None and r.completed_at is not None
        assert len(r.findings) >= 1
        assert any(f.category == "security" for f in r.findings)


# --- The four persisted outcomes (deterministic via FakeProvider) ---------------


def test_completed_with_rejected_count(worker_scope, monkeypatch):
    raw = '{"findings": [%s, {"severity": "fatal", "line_start": 1, "line_end": 1, \
"category": "bug", "description": "x", "rationale": "y"}]}' % _as_json(_valid_finding())
    _use_provider(monkeypatch, FakeProvider(raw=raw))
    sid = _seed_snippet(worker_scope)
    rid = _enqueue(worker_scope, sid)

    asyncio.run(worker.process_next())

    with worker_scope() as db:
        r = db.get(Review, rid)
        assert r.status == "completed"
        assert len(r.findings) == 1
        assert r.rejected_finding_count == 1


def test_zero_findings_completes(worker_scope, monkeypatch):
    _use_provider(monkeypatch, FakeProvider(raw='{"findings": []}'))
    sid = _seed_snippet(worker_scope)
    rid = _enqueue(worker_scope, sid)

    asyncio.run(worker.process_next())

    with worker_scope() as db:
        r = db.get(Review, rid)
        assert r.status == "completed"
        assert r.findings == []
        assert r.rejected_finding_count == 0


def test_all_invalid_fails(worker_scope, monkeypatch):
    raw = '{"findings": [{"severity": "fatal", "line_start": 1, "line_end": 1, \
"category": "bug", "description": "x", "rationale": "y"}]}'
    _use_provider(monkeypatch, FakeProvider(raw=raw))
    sid = _seed_snippet(worker_scope)
    rid = _enqueue(worker_scope, sid)

    asyncio.run(worker.process_next())

    with worker_scope() as db:
        r = db.get(Review, rid)
        assert r.status == "failed"
        assert r.findings == []
        assert r.error_message


def test_unexpected_error_marks_failed_not_stuck_running(worker_scope, monkeypatch):
    # A non-ProviderError after the claim (here: get_provider blows up) must still move the
    # review out of `running`, or the snippet would be locked behind 409 until a restart.
    sid = _seed_snippet(worker_scope)
    rid = _enqueue(worker_scope, sid)

    def boom(_settings=None):
        raise RuntimeError("provider config exploded")

    monkeypatch.setattr(worker, "get_provider", boom)
    asyncio.run(worker.process_next())  # claims (running) then hits the error

    with worker_scope() as db:
        r = db.get(Review, rid)
        assert r.status == "failed"  # not stuck running
        assert r.findings == []
        assert r.error_message


def test_malformed_output_fails(worker_scope, monkeypatch):
    _use_provider(monkeypatch, FakeProvider(raw="not json at all"))
    sid = _seed_snippet(worker_scope)
    rid = _enqueue(worker_scope, sid)

    asyncio.run(worker.process_next())

    with worker_scope() as db:
        r = db.get(Review, rid)
        assert r.status == "failed"
        assert r.findings == []


def test_provider_error_fails_with_sanitized_message(worker_scope, monkeypatch):
    _use_provider(monkeypatch, FakeProvider(error="connection refused to 10.0.0.5"))
    sid = _seed_snippet(worker_scope)
    rid = _enqueue(worker_scope, sid)

    asyncio.run(worker.process_next())

    with worker_scope() as db:
        r = db.get(Review, rid)
        assert r.status == "failed"
        # The sanitized message must not leak the raw provider error (e.g. the IP).
        assert "10.0.0.5" not in (r.error_message or "")
        assert r.error_message


# --- Persistence-failure fallback (Adjustment 2) --------------------------------


def test_persistence_failure_marks_failed_without_partial_findings(worker_scope, monkeypatch):
    sid = _seed_snippet(worker_scope)
    rid = _enqueue(worker_scope, sid)
    worker.claim_next_queued()  # move to running

    # Inject a failure while writing the completed result.
    def boom(_db, _review, _result):
        raise RuntimeError("simulated disk failure")

    monkeypatch.setattr(worker, "_apply_result", boom)
    result = ValidatedReview(status="completed", findings=[_valid_finding()], rejected_count=0)
    worker._persist_result(rid, result)

    with worker_scope() as db:
        r = db.get(Review, rid)
        assert r.status == "failed"  # not stuck running
        assert r.findings == []  # no partial findings committed
        assert r.error_message


# --- Startup recovery -----------------------------------------------------------


def test_recovery_fails_running_preserves_queued(worker_scope):
    # Two snippets: one has a review left `running` by a crash, the other a `queued` one.
    # (The partial index forbids a running AND a queued review on the SAME snippet.)
    sid_running = _seed_snippet(worker_scope)
    sid_queued = _seed_snippet(worker_scope)
    with worker_scope() as db:
        rid_running = Review(snippet_id=sid_running, run_number=1, status="running")
        rid_queued = Review(snippet_id=sid_queued, run_number=1, status="queued")
        db.add(rid_running)
        db.add(rid_queued)
        db.flush()
        running_id, queued_id = rid_running.id, rid_queued.id

    recovered = worker.recover_interrupted_reviews()
    assert recovered == 1

    with worker_scope() as db:
        assert db.get(Review, running_id).status == "failed"
        assert db.get(Review, running_id).error_message
        assert db.get(Review, queued_id).status == "queued"


# --- Concurrency-safe enqueue (Adjustment 1, real threads) ----------------------


def test_concurrent_enqueue_one_wins_one_conflicts(session_factory, worker_scope):
    sid = _seed_snippet(worker_scope)

    def attempt():
        db = session_factory()
        try:
            return worker.enqueue_review(db, sid)
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as ex:
        results = [f.result() for f in [ex.submit(attempt), ex.submit(attempt)]]

    created = [c for c, a in results if c is not None]
    conflicts = [a for c, a in results if a is not None]
    assert len(created) == 1
    assert len(conflicts) == 1
    # Only one active review row exists for the snippet.
    with worker_scope() as db:
        active = db.query(Review).filter(
            Review.snippet_id == sid, Review.status.in_(("queued", "running"))
        ).count()
        assert active == 1


def test_run_number_increments_after_completion(worker_scope):
    sid = _seed_snippet(worker_scope)
    rid1 = _enqueue(worker_scope, sid)
    with worker_scope() as db:
        db.get(Review, rid1).status = "completed"
    rid2 = _enqueue(worker_scope, sid)
    with worker_scope() as db:
        assert db.get(Review, rid2).run_number == 2


# --- A failed run must not disturb a prior successful run's findings -------------


def test_failed_run_preserves_prior_findings(worker_scope, monkeypatch):
    sid = _seed_snippet(worker_scope)

    # Run 1: completes with a finding.
    _use_provider(monkeypatch, FakeProvider(raw='{"findings": [%s]}' % _as_json(_valid_finding())))
    rid1 = _enqueue(worker_scope, sid)
    asyncio.run(worker.process_next())
    with worker_scope() as db:
        db.get(Review, rid1).status  # touch
        assert len(db.get(Review, rid1).findings) == 1

    # Run 2: fails.
    _use_provider(monkeypatch, FakeProvider(error="boom"))
    rid2 = _enqueue(worker_scope, sid)
    asyncio.run(worker.process_next())

    with worker_scope() as db:
        r1 = db.get(Review, rid1)
        r2 = db.get(Review, rid2)
        assert r1.status == "completed" and len(r1.findings) == 1  # untouched
        assert r2.status == "failed" and r2.findings == []


def _as_json(d: dict) -> str:
    import json

    return json.dumps(d)
