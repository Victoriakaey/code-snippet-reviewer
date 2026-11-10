# Code Snippet Reviewer

A lightweight, self-service tool for AI-powered review of ad-hoc code snippets.
Submit a snippet, trigger an LLM review, and work through the structured findings —
accept, dismiss, or discuss each one.

> **Status:** backend M1–M4 + frontend core (M5) + **per-finding discussion (M6)**. The full
> journey works in the browser: dashboard → create a snippet (CodeMirror) → run a review →
> inspect findings (severity-marked code, finding↔line nav) → accept/dismiss/reopen with a
> reason → discuss a finding with the AI. Final integration/docs (M7) remain.

## Stack

- **Frontend:** React + TypeScript + Vite
- **Backend:** FastAPI + Pydantic
- **Database:** SQLite + SQLAlchemy (foreign keys + WAL enabled)
- **AI:** Ollama-first (local), selected via `LLM_PROVIDER`; optional cloud provider later

## Run it

### Option A — one command (Docker)

```bash
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend health: http://localhost:8000/api/health

### Option B — without Docker (lighter on memory)

Backend (terminal 1):

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Frontend (terminal 2):

```bash
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173 — it should show **"✓ Backend OK · provider: ollama"**.

## Configuration

Copy `backend/.env.example` to `backend/.env` and adjust. Key variables:

- `LLM_PROVIDER` — which review provider to use. No automatic fallback between providers.
  - `ollama` (default) — the real local review provider.
  - `mock` — a deterministic stand-in that needs no model; it exercises the full app flow
    but produces placeholder findings, **not** a real review.
  - `openai` — documented but **not implemented in this version**; selecting it fails with a
    clear error. (A cloud adapter is future work.)
- `OLLAMA_BASE_URL`, `OLLAMA_MODEL` — local model. Install Ollama and pull a code model,
  e.g. `ollama pull qwen2.5-coder:7b` (any local tag works; set `OLLAMA_MODEL` to match).
- `DATABASE_URL` — SQLite file path.

> No Ollama installed? Set `LLM_PROVIDER=mock` to run the app end-to-end with deterministic
> placeholder findings. Real AI review requires a local model via Ollama.

### Trying the review provider (M2)

The review pipeline is wired into an HTTP endpoint only in M3. To sanity-check a real model
now, run the smoke script against a running Ollama:

```bash
cd backend
OLLAMA_MODEL=<your-local-tag> .venv/bin/python scripts/ollama_smoke.py
```

It reviews three snippets and prints findings, latency, and validation outcomes. A
structurally valid response proves the output is well-formed and in-range — never that a
finding is semantically correct.

## API (current)

- `POST /api/snippets` — create a snippet (`title`, `language`, `code`) → `201`. Validation
  failures (empty title/code, unsupported language, oversized input) → `422`.
- `GET /api/snippets` — list snippets, newest first, each with a derived status.
- `GET /api/snippets/{id}` — one snippet, or `404`.
- `POST /api/snippets/{id}/reviews` — trigger a review → `202` + a `queued` review. `409`
  (with the active review's id) if one is already in progress; `404` if the snippet is gone.
- `GET /api/reviews/{id}` — poll a review: `queued` / `running` / `completed` (with findings)
  / `failed` (with a sanitized error). Provenance (provider, model, rubric/prompt version) is
  stored per review.
- `PATCH /api/findings/{id}` — record a human decision on a finding: `open` / `accepted` /
  `dismissed` + an optional reason (≤ 1000 chars). Idempotent; only findings of a snippet's
  latest review are mutable (older runs are read-only → `409`); `404` for an unknown id.
- `POST /api/findings/{id}/messages` — ask a finding-grounded question; the user + AI replies
  are saved atomically (nothing is saved on failure → `503`); historical findings → `409`.
- `GET /api/findings/{id}/messages` — the discussion thread (readable for any finding).
- `GET /api/rubric` — the static versioned rubric.
- `GET /api/health` — liveness only.

Reviews run on a single in-process background worker (one at a time per the local-model
assumption). It is designed for a **single API process** — running multiple workers would
break startup crash-recovery. A review interrupted by a restart is marked `failed` on the
next start; `queued` reviews are preserved.

Supported languages: Python, JavaScript, TypeScript, Java, Go. Limits: title ≤ 200 chars,
code ≤ 50,000 chars.

## Data model & persistence

Four tables (`snippets`, `reviews`, `findings`, `finding_messages`). Enums and line ranges
are enforced as SQLite `CHECK` constraints; at most one active review per snippet is
enforced by a partial unique index; foreign keys are enforced (`PRAGMA foreign_keys=ON`).

Tables are created on startup with SQLAlchemy `create_all()`, which only creates missing
tables (it does not alter existing ones). A tiny idempotent helper (`ensure_schema`) adds any
missing **additive** columns to a pre-existing table on startup and fails loudly if it can't,
so an older local database is upgraded without data loss. This is a deliberate minimal
stand-in — a production deployment would manage schema changes with **Alembic** (out of
scope here).

## Tests

```bash
cd backend && pytest -q
```

## Architecture & decisions

Design rationale, data model, API contracts, and trade-offs are documented and will be
summarized here as the milestones land. (Internal planning notes live outside the
submission.)
