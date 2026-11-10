"""Review history (CP2): the read-only run-list endpoint + the dashboard review-run count,
and regression coverage that historical runs stay read-only at the API level (not just the UI).
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import Finding, Review, Snippet


def _finding(review_id: str, line: int = 1) -> Finding:
    return Finding(
        review_id=review_id,
        line_start=line,
        line_end=line,
        severity="warning",
        category="bug",
        description="d",
        rationale="r",
    )


def _snippet_with_runs(session_factory: sessionmaker, runs: list[tuple[int, str, int]]) -> str:
    """Create a snippet with the given review runs. `runs` = [(run_number, status, n_findings)].
    Returns the snippet id."""
    s = session_factory()
    try:
        snip = Snippet(title="t", language="python", code="x = 1\n")
        s.add(snip)
        s.flush()
        for run_number, status, n in runs:
            r = Review(snippet_id=snip.id, run_number=run_number, status=status,
                       provider="mock", model_name="mock-deterministic")
            s.add(r)
            s.flush()
            for i in range(n):
                s.add(_finding(r.id, line=i + 1))
        sid = snip.id
        s.commit()
        return sid
    finally:
        s.close()


# --- Dashboard review-run count --------------------------------------------------

def test_review_count_zero_when_never_reviewed(client: TestClient, session_factory):
    s = session_factory()
    try:
        snip = Snippet(title="fresh", language="python", code="x=1\n")
        s.add(snip)
        s.commit()
    finally:
        s.close()
    rows = client.get("/api/snippets").json()
    row = next(r for r in rows if r["title"] == "fresh")
    assert row["review_count"] == 0
    assert row["finding_count"] == 0


def test_review_count_counts_all_statuses(client: TestClient, session_factory):
    # completed + failed + queued = 3 runs; findings only on the completed one.
    sid = _snippet_with_runs(session_factory, [(1, "completed", 2), (2, "failed", 0), (3, "queued", 0)])
    row = next(r for r in client.get("/api/snippets").json() if r["id"] == sid)
    assert row["review_count"] == 3  # all statuses counted, not just completed
    # review_count is distinct from finding_count (last successful run's findings).
    assert row["finding_count"] == 2


def test_review_counts_independent_across_snippets(client: TestClient, session_factory):
    a = _snippet_with_runs(session_factory, [(1, "completed", 1)])
    b = _snippet_with_runs(session_factory, [(1, "completed", 1), (2, "failed", 0)])
    c_id = _snippet_with_runs(session_factory, [])  # created, zero runs
    counts = {r["id"]: r["review_count"] for r in client.get("/api/snippets").json()}
    assert counts[a] == 1
    assert counts[b] == 2
    assert counts[c_id] == 0


# --- Run-list endpoint -----------------------------------------------------------

def test_list_runs_newest_first_with_finding_counts(client: TestClient, session_factory):
    sid = _snippet_with_runs(session_factory, [(1, "completed", 1), (2, "completed", 3)])
    runs = client.get(f"/api/snippets/{sid}/reviews").json()
    assert [r["run_number"] for r in runs] == [2, 1]  # newest first
    by_run = {r["run_number"]: r for r in runs}
    assert by_run[2]["finding_count"] == 3
    assert by_run[1]["finding_count"] == 1


def test_list_runs_failed_run_shows_own_status_zero_findings(client: TestClient, session_factory):
    sid = _snippet_with_runs(session_factory, [(1, "completed", 2), (2, "failed", 0)])
    runs = client.get(f"/api/snippets/{sid}/reviews").json()
    failed = next(r for r in runs if r["run_number"] == 2)
    assert failed["status"] == "failed"
    assert failed["finding_count"] == 0  # a failed run never carries another run's findings


def test_list_runs_404_unknown_snippet(client: TestClient):
    assert client.get("/api/snippets/nope/reviews").status_code == 404


# --- Historical read-only is enforced at the API, not just the UI ----------------

def test_historical_finding_patch_rejected_at_api(client: TestClient, session_factory):
    # run #1 completed (with a finding) then a newer run #2 -> run #1's finding is historical.
    s = session_factory()
    try:
        snip = Snippet(title="t", language="python", code="x=1\n")
        s.add(snip); s.flush()
        r1 = Review(snippet_id=snip.id, run_number=1, status="completed")
        s.add(r1); s.flush()
        f = _finding(r1.id)
        s.add(f); s.flush()
        s.add(Review(snippet_id=snip.id, run_number=2, status="completed"))
        fid = f.id
        s.commit()
    finally:
        s.close()
    res = client.patch(f"/api/findings/{fid}", json={"resolution_status": "accepted"})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "finding_read_only"


def test_historical_discussion_post_rejected_at_api(client: TestClient, session_factory, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "mock")
    s = session_factory()
    try:
        snip = Snippet(title="t", language="python", code="x=1\n")
        s.add(snip); s.flush()
        r1 = Review(snippet_id=snip.id, run_number=1, status="completed")
        s.add(r1); s.flush()
        f = _finding(r1.id)
        s.add(f); s.flush()
        s.add(Review(snippet_id=snip.id, run_number=2, status="completed"))
        fid = f.id
        s.commit()
    finally:
        s.close()
    res = client.post(f"/api/findings/{fid}/messages", json={"question": "hi"})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "finding_read_only"
    assert client.get(f"/api/findings/{fid}/messages").json() == []
