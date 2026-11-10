"""Snippet CRUD API tests: create / list / get, derived status, and validation 422s."""
from __future__ import annotations

from fastapi.testclient import TestClient

VALID = {"title": "Fibonacci", "language": "python", "code": "def fib(n): return n"}


def test_create_returns_201_and_body(client: TestClient):
    res = client.post("/api/snippets", json=VALID)
    assert res.status_code == 201
    body = res.json()
    assert body["id"]
    assert body["title"] == "Fibonacci"
    assert body["language"] == "python"
    assert body["code"] == VALID["code"]
    assert body["status"] == "not_reviewed"  # no reviews yet
    assert "created_at" in body


def test_title_is_trimmed(client: TestClient):
    res = client.post("/api/snippets", json={**VALID, "title": "  spaced  "})
    assert res.status_code == 201
    assert res.json()["title"] == "spaced"


def test_list_returns_created_snippets_newest_first(client: TestClient):
    first = client.post("/api/snippets", json={**VALID, "title": "first"}).json()
    second = client.post("/api/snippets", json={**VALID, "title": "second"}).json()
    res = client.get("/api/snippets")
    assert res.status_code == 200
    ids = [s["id"] for s in res.json()]
    assert first["id"] in ids and second["id"] in ids
    # newest first
    assert ids.index(second["id"]) < ids.index(first["id"])


def test_get_by_id(client: TestClient):
    created = client.post("/api/snippets", json=VALID).json()
    res = client.get(f"/api/snippets/{created['id']}")
    assert res.status_code == 200
    assert res.json()["id"] == created["id"]


def test_get_unknown_id_returns_404_envelope(client: TestClient):
    res = client.get("/api/snippets/missing-id")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"


# --- Validation (422 + error envelope) ------------------------------------------


def test_empty_title_rejected(client: TestClient):
    res = client.post("/api/snippets", json={**VALID, "title": "   "})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_error"


def test_empty_code_rejected(client: TestClient):
    res = client.post("/api/snippets", json={**VALID, "code": "   "})
    assert res.status_code == 422


def test_bad_language_rejected(client: TestClient):
    res = client.post("/api/snippets", json={**VALID, "language": "cobol"})
    assert res.status_code == 422


def test_oversized_title_rejected(client: TestClient):
    res = client.post("/api/snippets", json={**VALID, "title": "x" * 201})
    assert res.status_code == 422


def test_oversized_code_rejected(client: TestClient):
    res = client.post("/api/snippets", json={**VALID, "code": "x" * 50_001})
    assert res.status_code == 422


def test_missing_field_rejected(client: TestClient):
    res = client.post("/api/snippets", json={"title": "t", "language": "python"})
    assert res.status_code == 422


def test_all_five_languages_accepted(client: TestClient):
    for lang in ("python", "javascript", "typescript", "java", "go"):
        res = client.post("/api/snippets", json={**VALID, "language": lang})
        assert res.status_code == 201, lang
