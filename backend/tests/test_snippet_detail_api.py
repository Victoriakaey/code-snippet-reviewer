"""Dashboard list enrichment (reviewer + finding count), the E2 detail shape, and the
static rubric endpoint.
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


def _seed(session_factory: sessionmaker, reviews: list[tuple[int, str, int]]):
    """reviews = list of (run_number, status, n_findings). Returns (snippet_id, review_ids)."""
    s = session_factory()
    try:
        snip = Snippet(title="t", language="python", code="x = 1\ny = 2\n")
        s.add(snip)
        s.flush()
        ids = []
        for run, status, n in reviews:
            rev = Review(
                snippet_id=snip.id, run_number=run, status=status,
                model_name="qwen-test" if status == "completed" else None,
            )
            s.add(rev)
            s.flush()
            for _ in range(n):
                s.add(_finding(rev.id))
            ids.append(rev.id)
        s.flush()
        sid = snip.id
        s.commit()
        return sid, ids
    finally:
        s.close()


# --- Dashboard list -------------------------------------------------------------


def test_list_includes_reviewer_and_finding_count(client: TestClient, session_factory):
    sid, _ = _seed(session_factory, [(1, "completed", 2)])
    row = next(r for r in client.get("/api/snippets").json() if r["id"] == sid)
    assert row["status"] == "reviewed"
    assert row["reviewer"] == "qwen-test"
    assert row["finding_count"] == 2


def test_list_no_reviews_has_null_reviewer(client: TestClient, session_factory):
    sid, _ = _seed(session_factory, [])
    row = next(r for r in client.get("/api/snippets").json() if r["id"] == sid)
    assert row["status"] == "not_reviewed"
    assert row["reviewer"] is None
    assert row["finding_count"] == 0


# --- E2 detail ------------------------------------------------------------------


def test_detail_completed_latest_equals_displayed(client: TestClient, session_factory):
    sid, [rid] = _seed(session_factory, [(1, "completed", 1)])
    body = client.get(f"/api/snippets/{sid}").json()
    assert body["status"] == "reviewed"
    assert body["latest_review"]["id"] == rid
    assert body["displayed_review"]["id"] == rid  # same run -> findings are current
    assert len(body["findings"]) == 1


def test_detail_historical_when_latest_failed(client: TestClient, session_factory):
    # run1 completed (has findings), run2 failed (latest). Findings shown are run1's.
    sid, [rid1, rid2] = _seed(session_factory, [(1, "completed", 1), (2, "failed", 0)])
    body = client.get(f"/api/snippets/{sid}").json()
    assert body["status"] == "failed"  # latest attempt failed
    assert body["latest_review"]["id"] == rid2
    assert body["displayed_review"]["id"] == rid1  # historical: differs from latest
    assert body["latest_review"]["id"] != body["displayed_review"]["id"]
    assert len(body["findings"]) == 1  # the old successful run's findings


def test_detail_no_reviews(client: TestClient, session_factory):
    sid, _ = _seed(session_factory, [])
    body = client.get(f"/api/snippets/{sid}").json()
    assert body["status"] == "not_reviewed"
    assert body["latest_review"] is None
    assert body["displayed_review"] is None
    assert body["findings"] == []


def test_detail_404(client: TestClient):
    assert client.get("/api/snippets/nope").status_code == 404


# --- Rubric ---------------------------------------------------------------------


def test_rubric_endpoint(client: TestClient):
    body = client.get("/api/rubric").json()
    assert body["rubric_version"] == "v2"
    assert body["prompt_version"] == "v2"
    assert {d["category"] for d in body["dimensions"]} == {
        "bug", "security", "performance", "maintainability"
    }
    assert {s["severity"] for s in body["severities"]} == {"critical", "warning", "info"}
