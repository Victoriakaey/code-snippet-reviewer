# Code Snippet Reviewer

A lightweight, self-service tool for AI-powered review of ad-hoc code snippets.
Submit a snippet, trigger an LLM review, and work through the structured findings —
accept, dismiss, or discuss each one.

> **Status:** data model + snippet CRUD (M1). The AI review pipeline and the UI land in
> later milestones. The commands below start the current backend (snippet create/list/get
> + health) and the frontend skeleton.

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

- `LLM_PROVIDER` — `ollama` (default) or `openai`. No automatic fallback between them.
- `OLLAMA_BASE_URL`, `OLLAMA_MODEL` — local model (run `ollama pull qwen2.5-coder:7b`).
- `OPENAI_API_KEY`, `OPENAI_MODEL` — only used when `LLM_PROVIDER=openai`; kept server-side.
- `DATABASE_URL` — SQLite file path.

> Reviewers without Ollama installed can set `LLM_PROVIDER=openai` with an API key once the
> review pipeline lands (M2).

## API (current)

- `POST /api/snippets` — create a snippet (`title`, `language`, `code`) → `201`. Validation
  failures (empty title/code, unsupported language, oversized input) → `422`.
- `GET /api/snippets` — list snippets, newest first, each with a derived status.
- `GET /api/snippets/{id}` — one snippet, or `404`.
- `GET /api/health` — liveness only.

Supported languages: Python, JavaScript, TypeScript, Java, Go. Limits: title ≤ 200 chars,
code ≤ 50,000 chars.

## Data model & persistence

Four tables (`snippets`, `reviews`, `findings`, `finding_messages`). Enums and line ranges
are enforced as SQLite `CHECK` constraints; at most one active review per snippet is
enforced by a partial unique index; foreign keys are enforced (`PRAGMA foreign_keys=ON`).

Tables are created on startup with SQLAlchemy `create_all()`. **This does not migrate an
existing schema** — it only creates missing tables. A production deployment would manage
schema changes with a migration tool such as **Alembic** (intentionally out of scope here).

## Tests

```bash
cd backend && pytest -q
```

## Architecture & decisions

Design rationale, data model, API contracts, and trade-offs are documented and will be
summarized here as the milestones land. (Internal planning notes live outside the
submission.)
