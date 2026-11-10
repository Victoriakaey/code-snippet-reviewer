import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "llm_provider" in body


@pytest.mark.parametrize("provider", ["ollama", "openai"])
def test_health_reflects_configured_provider(monkeypatch, provider):
    # We deliberately do NOT hardcode the default: Settings reads .env, and the README
    # tells reviewers without Ollama to set LLM_PROVIDER=openai, so pinning "ollama"
    # would fail for them. Instead, patch the configured provider to a known value and
    # assert the endpoint echoes EXACTLY that. The expected value is independent of
    # settings.llm_provider, so this catches a hardcoded response (which would ignore
    # the config) without depending on which provider is actually installed. It verifies
    # config echo only — that both providers actually RUN is M2's concern.
    monkeypatch.setattr(settings, "llm_provider", provider)
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["llm_provider"] == provider
