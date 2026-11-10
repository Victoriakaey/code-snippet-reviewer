"""Regression: a provider that cannot be constructed (e.g. LLM_PROVIDER=openai with no
OPENAI_API_KEY) must surface as a sanitized 503 in the shared error envelope — never an
unhandled HTTP 500 — on BOTH the review-create and discussion endpoints, and must not leave
a half-created review or a half-written discussion thread behind.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import Finding, Review, Snippet


def _seed_finding(session_factory: sessionmaker) -> str:
    """One snippet + a completed (latest) review + a finding. Returns the finding id."""
    s = session_factory()
    try:
        snip = Snippet(title="t", language="python", code="def f(x=[]):\n    return x\n")
        s.add(snip)
        s.flush()
        r = Review(snippet_id=snip.id, run_number=1, status="completed")
        s.add(r)
        s.flush()
        f = Finding(
            review_id=r.id, line_start=1, line_end=1,
            severity="warning", category="bug", description="d", rationale="r",
        )
        s.add(f)
        s.flush()
        fid = f.id
        s.commit()
        return fid
    finally:
        s.close()


def _use_openai_without_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "")


def test_create_review_missing_key_returns_503_not_500(client: TestClient, monkeypatch):
    _use_openai_without_key(monkeypatch)
    sid = client.post(
        "/api/snippets", json={"title": "t", "language": "python", "code": "x = 1\n"}
    ).json()["id"]

    res = client.post(f"/api/snippets/{sid}/reviews")

    assert res.status_code == 503  # the whole point: not an unhandled 500
    body = res.json()
    assert body["error"]["code"] == "provider_unavailable"
    msg = body["error"]["message"]
    assert "OPENAI_API_KEY" in msg  # clear, actionable config hint
    assert "Traceback" not in msg and "sk-" not in msg  # sanitized: no stack, no secret value
    # No half-created review: the provider is validated BEFORE any row is inserted.
    assert client.get(f"/api/snippets/{sid}/reviews").json() == []


def test_create_review_mock_still_succeeds(client: TestClient, monkeypatch):
    # Positive control: the new handler must not disturb the working provider path.
    monkeypatch.setattr(settings, "llm_provider", "mock")
    sid = client.post(
        "/api/snippets", json={"title": "t", "language": "python", "code": "x = 1\n"}
    ).json()["id"]
    res = client.post(f"/api/snippets/{sid}/reviews")
    assert res.status_code == 202


def test_discuss_missing_key_returns_503_not_500(client: TestClient, session_factory, monkeypatch):
    fid = _seed_finding(session_factory)
    _use_openai_without_key(monkeypatch)

    res = client.post(f"/api/findings/{fid}/messages", json={"question": "why is this bad?"})

    assert res.status_code == 503  # not an unhandled 500
    body = res.json()
    assert body["error"]["code"] == "provider_unavailable"
    assert "Traceback" not in body["error"]["message"] and "sk-" not in body["error"]["message"]
    # No half-written thread: get_provider fails before anything is persisted.
    assert client.get(f"/api/findings/{fid}/messages").json() == []
