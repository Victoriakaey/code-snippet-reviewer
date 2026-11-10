"""Finding resolution API (M4): accept/dismiss/reopen, optional reason, the omitted-vs-null
distinction, resolved_at rules, idempotency, validation, and backend-enforced historical
read-only.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.models import Finding, Review, Snippet


def _finding(review_id: str) -> Finding:
    return Finding(
        review_id=review_id,
        line_start=1,
        line_end=1,
        severity="warning",
        category="bug",
        description="d",
        rationale="r",
    )


def _seed_finding(session_factory: sessionmaker) -> str:
    """One snippet, one completed (latest) review, one open finding -> finding id."""
    s = session_factory()
    try:
        snip = Snippet(title="t", language="python", code="x = 1\n")
        s.add(snip)
        s.flush()
        rev = Review(snippet_id=snip.id, run_number=1, status="completed")
        s.add(rev)
        s.flush()
        f = _finding(rev.id)
        s.add(f)
        s.flush()
        fid = f.id
        s.commit()
        return fid
    finally:
        s.close()


def _seed_historical(session_factory: sessionmaker, latest_status: str = "completed"):
    """A snippet with an older completed review (finding F1) and a newer latest review.
    Returns (old_finding_id, latest_finding_id_or_None, latest_review_id)."""
    s = session_factory()
    try:
        snip = Snippet(title="t", language="python", code="x = 1\n")
        s.add(snip)
        s.flush()
        rev1 = Review(snippet_id=snip.id, run_number=1, status="completed")
        s.add(rev1)
        s.flush()
        f1 = _finding(rev1.id)
        s.add(f1)
        s.flush()
        rev2 = Review(snippet_id=snip.id, run_number=2, status=latest_status)
        s.add(rev2)
        s.flush()
        latest_fid = None
        if latest_status == "completed":
            f2 = _finding(rev2.id)
            s.add(f2)
            s.flush()
            latest_fid = f2.id
        old_id, rev2_id = f1.id, rev2.id
        s.commit()
        return old_id, latest_fid, rev2_id
    finally:
        s.close()


def _patch(client, fid, body):
    return client.patch(f"/api/findings/{fid}", json=body)


# --- Accept / dismiss / reopen --------------------------------------------------


def test_accept_sets_status_and_resolved_at(client: TestClient, session_factory):
    fid = _seed_finding(session_factory)
    res = _patch(client, fid, {"resolution_status": "accepted"})
    assert res.status_code == 200
    body = res.json()
    assert body["resolution_status"] == "accepted"
    assert body["resolved_at"] is not None


def test_dismiss_with_reason(client: TestClient, session_factory):
    fid = _seed_finding(session_factory)
    res = _patch(
        client, fid, {"resolution_status": "dismissed", "resolution_reason": "false alarm"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["resolution_status"] == "dismissed"
    assert body["resolution_reason"] == "false alarm"
    assert body["resolved_at"] is not None


def test_reopen_clears_reason_and_resolved_at(client: TestClient, session_factory):
    fid = _seed_finding(session_factory)
    _patch(client, fid, {"resolution_status": "accepted", "resolution_reason": "ok"})
    res = _patch(client, fid, {"resolution_status": "open"})
    body = res.json()
    assert body["resolution_status"] == "open"
    assert body["resolution_reason"] is None
    assert body["resolved_at"] is None


# --- resolved_at rules ----------------------------------------------------------


def test_editing_reason_keeps_resolved_at(client: TestClient, session_factory):
    fid = _seed_finding(session_factory)
    first = _patch(
        client, fid, {"resolution_status": "accepted", "resolution_reason": "A"}
    ).json()
    edited = _patch(
        client, fid, {"resolution_status": "accepted", "resolution_reason": "B"}
    ).json()
    assert edited["resolution_reason"] == "B"
    assert edited["resolved_at"] == first["resolved_at"]  # unchanged on a reason edit


def test_status_switch_refreshes_resolved_at(client: TestClient, session_factory):
    fid = _seed_finding(session_factory)
    accepted = _patch(client, fid, {"resolution_status": "accepted"}).json()
    dismissed = _patch(client, fid, {"resolution_status": "dismissed"}).json()
    assert dismissed["resolved_at"] is not None
    assert dismissed["resolved_at"] != accepted["resolved_at"]  # switch -> refreshed


# --- Idempotency ----------------------------------------------------------------


def test_identical_repeat_is_idempotent(client: TestClient, session_factory):
    fid = _seed_finding(session_factory)
    first = _patch(
        client, fid, {"resolution_status": "accepted", "resolution_reason": "ok"}
    ).json()
    again = _patch(
        client, fid, {"resolution_status": "accepted", "resolution_reason": "ok"}
    ).json()
    assert again["resolved_at"] == first["resolved_at"]
    assert again["resolution_reason"] == first["resolution_reason"]
    assert again["resolution_status"] == "accepted"


# --- Omitted vs explicit null ---------------------------------------------------


def test_omitted_reason_preserves_existing(client: TestClient, session_factory):
    fid = _seed_finding(session_factory)
    _patch(client, fid, {"resolution_status": "accepted", "resolution_reason": "keep me"})
    res = _patch(client, fid, {"resolution_status": "accepted"}).json()  # omitted
    assert res["resolution_reason"] == "keep me"


def test_explicit_null_clears_reason(client: TestClient, session_factory):
    fid = _seed_finding(session_factory)
    _patch(client, fid, {"resolution_status": "accepted", "resolution_reason": "drop me"})
    res = _patch(
        client, fid, {"resolution_status": "accepted", "resolution_reason": None}
    ).json()
    assert res["resolution_reason"] is None


def test_status_change_with_omitted_reason_clears_old(client: TestClient, session_factory):
    fid = _seed_finding(session_factory)
    _patch(client, fid, {"resolution_status": "accepted", "resolution_reason": "accept note"})
    res = _patch(client, fid, {"resolution_status": "dismissed"}).json()  # omitted
    assert res["resolution_reason"] is None  # accept reason must not carry into dismiss


def test_whitespace_reason_normalized_to_null(client: TestClient, session_factory):
    fid = _seed_finding(session_factory)
    res = _patch(
        client, fid, {"resolution_status": "accepted", "resolution_reason": "   "}
    ).json()
    assert res["resolution_reason"] is None


# --- Validation + not found -----------------------------------------------------


def test_reason_too_long_422(client: TestClient, session_factory):
    fid = _seed_finding(session_factory)
    res = _patch(
        client, fid, {"resolution_status": "accepted", "resolution_reason": "x" * 1001}
    )
    assert res.status_code == 422


def test_invalid_status_422(client: TestClient, session_factory):
    fid = _seed_finding(session_factory)
    res = _patch(client, fid, {"resolution_status": "maybe"})
    assert res.status_code == 422


def test_unknown_finding_404(client: TestClient):
    res = _patch(client, "missing", {"resolution_status": "accepted"})
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"


# --- Historical read-only (backend-enforced) ------------------------------------


def test_latest_review_finding_is_mutable(client: TestClient, session_factory):
    _old, latest_fid, _rid = _seed_historical(session_factory)
    res = _patch(client, latest_fid, {"resolution_status": "accepted"})
    assert res.status_code == 200


def test_historical_finding_is_read_only_409(client: TestClient, session_factory):
    old_fid, _latest, _rid = _seed_historical(session_factory)
    res = _patch(client, old_fid, {"resolution_status": "accepted"})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "finding_read_only"


def test_historical_read_only_even_when_latest_failed(client: TestClient, session_factory):
    # Latest review failed (no findings of its own); the older run's findings stay read-only.
    old_fid, latest, _rid = _seed_historical(session_factory, latest_status="failed")
    assert latest is None
    res = _patch(client, old_fid, {"resolution_status": "accepted"})
    assert res.status_code == 409


# --- Visible through GET /api/reviews/{id} --------------------------------------


def test_resolution_visible_via_get_review(client: TestClient, session_factory):
    _old, latest_fid, rid = _seed_historical(session_factory)
    _patch(client, latest_fid, {"resolution_status": "dismissed", "resolution_reason": "nit"})
    review = client.get(f"/api/reviews/{rid}").json()
    target = next(f for f in review["findings"] if f["id"] == latest_fid)
    assert target["resolution_status"] == "dismissed"
    assert target["resolution_reason"] == "nit"
