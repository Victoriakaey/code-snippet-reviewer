"""Finding discussion API (M6): atomic pair persistence, failure saves nothing, historical
read-only, provenance on the assistant message, validation, and the thread GET.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import Finding, Review, Snippet
from app.providers import ProviderError


def _finding(review_id: str) -> Finding:
    return Finding(
        review_id=review_id,
        line_start=1,
        line_end=1,
        severity="warning",
        category="bug",
        description="mutable default arg",
        rationale="shared across calls",
    )


def _seed(session_factory: sessionmaker, extra_latest: str | None = None) -> str:
    """One snippet + a completed review + a finding. If extra_latest is given, add a newer
    review of that status (making the first finding historical). Returns the finding id."""
    s = session_factory()
    try:
        snip = Snippet(title="t", language="python", code="def f(x=[]):\n    return x\n")
        s.add(snip)
        s.flush()
        r1 = Review(snippet_id=snip.id, run_number=1, status="completed")
        s.add(r1)
        s.flush()
        f = _finding(r1.id)
        s.add(f)
        s.flush()
        if extra_latest:
            s.add(Review(snippet_id=snip.id, run_number=2, status=extra_latest))
        fid = f.id
        s.commit()
        return fid
    finally:
        s.close()


def test_discuss_persists_user_and_assistant_atomically(client: TestClient, session_factory, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "mock")
    fid = _seed(session_factory)
    res = client.post(f"/api/findings/{fid}/messages", json={"question": "why is this bad?"})
    assert res.status_code == 200
    thread = res.json()
    assert len(thread) == 2
    user, assistant = thread
    assert user["role"] == "user" and user["content"] == "why is this bad?"
    assert user["provider"] is None and user["model_name"] is None  # null on user msg
    assert assistant["role"] == "assistant"
    assert assistant["provider"] == "mock"  # provenance recorded
    assert assistant["model_name"] == "mock-deterministic"


def test_discuss_failure_saves_nothing(client: TestClient, session_factory, monkeypatch):
    class Boom:
        name = "mock"
        model_name = "mock-deterministic"

        async def discuss(self, **_kw):
            raise ProviderError("model down")

    monkeypatch.setattr("app.routers.messages.get_provider", lambda _s=None: Boom())
    fid = _seed(session_factory)
    res = client.post(f"/api/findings/{fid}/messages", json={"question": "explain"})
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "discuss_failed"
    # No half thread.
    assert client.get(f"/api/findings/{fid}/messages").json() == []


def test_discuss_on_historical_finding_409(client: TestClient, session_factory, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "mock")
    fid = _seed(session_factory, extra_latest="completed")  # a newer review exists
    res = client.post(f"/api/findings/{fid}/messages", json={"question": "hi"})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "finding_read_only"
    assert client.get(f"/api/findings/{fid}/messages").json() == []


def test_discuss_historical_when_latest_queued_409(client: TestClient, session_factory, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "mock")
    fid = _seed(session_factory, extra_latest="queued")
    assert client.post(f"/api/findings/{fid}/messages", json={"question": "hi"}).status_code == 409


def test_get_thread_after_two_turns(client: TestClient, session_factory, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "mock")
    fid = _seed(session_factory)
    client.post(f"/api/findings/{fid}/messages", json={"question": "q1"})
    client.post(f"/api/findings/{fid}/messages", json={"question": "q2"})
    thread = client.get(f"/api/findings/{fid}/messages").json()
    assert len(thread) == 4  # two user + two assistant
    assert [m["role"] for m in thread] == ["user", "assistant", "user", "assistant"]


def test_empty_question_422(client: TestClient, session_factory, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "mock")
    fid = _seed(session_factory)
    assert client.post(f"/api/findings/{fid}/messages", json={"question": "   "}).status_code == 422


def test_unknown_finding_404(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "mock")
    assert client.post("/api/findings/nope/messages", json={"question": "hi"}).status_code == 404
    assert client.get("/api/findings/nope/messages").status_code == 404
