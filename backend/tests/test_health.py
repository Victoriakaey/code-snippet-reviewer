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


def test_health_reflects_configured_provider():
    # Don't hardcode a provider value: Settings also reads .env, and the README tells
    # reviewers without Ollama to set LLM_PROVIDER=openai. Assert the endpoint echoes
    # whatever is configured, and that it is a known provider.
    res = client.get("/api/health")
    provider = res.json()["llm_provider"]
    assert provider == settings.llm_provider
    assert provider in {"ollama", "openai"}
