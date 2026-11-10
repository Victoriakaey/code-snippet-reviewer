from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "llm_provider" in body


def test_health_reports_default_provider():
    # Default provider is Ollama-first (no cloud fallback).
    res = client.get("/api/health")
    assert res.json()["llm_provider"] == "ollama"
