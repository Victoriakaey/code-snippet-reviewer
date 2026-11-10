"""Review API: enqueue (202), 404, the 409 active-conflict envelope, and GET polling.

These tests exercise the HTTP layer only — the background worker does not run under a plain
TestClient, so a review stays `queued` here. Worker processing is covered in test_worker.py.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

SNIPPET = {"title": "t", "language": "python", "code": "def f():\n    return 1\n"}


def _new_snippet(client: TestClient) -> str:
    return client.post("/api/snippets", json=SNIPPET).json()["id"]


def test_create_review_404_for_unknown_snippet(client: TestClient):
    res = client.post("/api/snippets/nope/reviews")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"


def test_create_review_returns_202_queued(client: TestClient):
    sid = _new_snippet(client)
    res = client.post(f"/api/snippets/{sid}/reviews")
    assert res.status_code == 202
    body = res.json()
    assert body["status"] == "queued"
    assert body["run_number"] == 1
    assert body["snippet_id"] == sid
    assert body["provider"]  # provenance stamped at enqueue
    assert body["findings"] == []


def test_second_review_conflicts_409_with_active_id(client: TestClient):
    sid = _new_snippet(client)
    first = client.post(f"/api/snippets/{sid}/reviews").json()
    res = client.post(f"/api/snippets/{sid}/reviews")
    assert res.status_code == 409
    err = res.json()["error"]
    assert err["code"] == "review_already_active"
    assert err["review_id"] == first["id"]


def test_get_review_404(client: TestClient):
    res = client.get("/api/reviews/missing")
    assert res.status_code == 404


def test_get_review_returns_queued_state(client: TestClient):
    sid = _new_snippet(client)
    rid = client.post(f"/api/snippets/{sid}/reviews").json()["id"]
    res = client.get(f"/api/reviews/{rid}")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == rid
    assert body["status"] == "queued"
    assert body["completed_at"] is None
    assert body["findings"] == []
