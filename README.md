# Code Snippet Reviewer

A lightweight, self-service tool for AI-powered review of ad-hoc code snippets.
Submit a snippet, trigger an LLM review, and work through the structured findings —
accept, dismiss, or discuss each one.

The full journey works in the browser: dashboard → create a snippet (CodeMirror) → run a
review → inspect findings (severity-marked code, finding↔line navigation) → accept / dismiss /
reopen with a reason → discuss a finding with the AI. See [`AI_USAGE.md`](./AI_USAGE.md) for an
honest account of how AI was used to build it.

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

**Ollama from inside Docker:** a container's `localhost` is the container, **not** your host,
so the backend cannot reach a host-installed Ollama via `localhost:11434`. The compose file
points the backend at the host with `OLLAMA_BASE_URL=http://host.docker.internal:11434`
(resolved on Linux by an `extra_hosts: host-gateway` entry). Start Ollama on the host first
(`ollama serve` + `ollama pull <model>`). **No Ollama?** Run the app end-to-end in Docker with
deterministic placeholder findings by setting `LLM_PROVIDER=mock` for the backend service.

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

> **Optional:** `backend/scripts/ollama_smoke.py` reviews three sample snippets against a
> running Ollama and prints findings, latency, and validation outcomes — a quick check that a
> local model responds in the expected shape (shape only, never semantic correctness).

## API

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

**Shape.** React/TypeScript/Vite frontend → FastAPI backend → SQLite (SQLAlchemy). A review is
not run in the request: `POST /reviews` only inserts a `queued` row and returns `202`; a single
in-process **background worker** claims it (`queued → running`), calls the model, validates the
output, and writes findings + the terminal status in **one transaction**. The frontend polls
`GET /reviews/{id}` (~1.5s) until a terminal state. Discussion is the opposite shape — a single
quick model call awaited in the request (it does not need the job machinery).

**Key decisions and trade-offs:**

- **Ollama-first, explicit provider, no auto-fallback.** `LLM_PROVIDER` selects the provider;
  choosing local never silently sends code to a cloud service (privacy), and a fixed provider
  keeps a run reproducible — every review stores the actual `provider` + `model_name`, shown in
  the UI. A `mock` provider gives deterministic, model-free runs for tests and demos.
- **The model proposes; it never writes the DB or runs code.** Output is validated before any
  write: bad JSON or all-invalid findings → the review `failed`; an individual invalid finding
  is **dropped and counted** (shown as "N filtered"), never clamped — forcing an out-of-range
  line would fabricate false evidence. Evidence shown in the UI is the *actual* snippet lines,
  derived from the immutable snippet, so the model cannot invent code. **Valid structure is not
  semantic truth** — the app never claims a finding is correct, only well-formed and in-range.
- **Immutable snippets.** A snippet has no `updated_at`; a finding's line range always refers to
  the exact code it was generated against, never shifted lines.
- **One active review per snippet, enforced by the database** (a partial unique index on
  `status IN ('queued','running')`), not by an application check — two concurrent enqueues can
  never both win.
- **Single-process worker + startup recovery.** On boot, `running` reviews (interrupted by a
  crash) are marked `failed`; `queued` ones are preserved. This assumes a single API process —
  running multiple workers would break recovery.
- **Discussion persistence is atomic.** The user question and the AI answer are saved together
  or not at all; a model/DB failure saves nothing and returns a retryable `503`. Older reviews'
  findings and discussions are read-only (resolutions and new messages are blocked with `409`).
- **Schema migration without Alembic (deliberate minimal stand-in).** `create_all()` builds
  missing tables; a tiny `ensure_schema()` adds missing additive columns on startup and fails
  loudly rather than running on a broken schema.

### Known limitations

- **Discussion is atomic but not exactly-once** under ambiguous network failures (a reply could
  be generated but the response lost); retrying is safe but may re-ask the model.
- **Grounding / premise-checking is not guaranteed.** The 7B model can still partly go along
  with a false premise in a question; the v2 discussion prompt reduces this but does not remove
  it.
- **The 20-message discussion history cap does not strictly bound total context size** — a few
  very long messages can still be large.
- **Dashboard `GET /api/snippets` is N+1** (a few queries per row) and two components
  (`SnippetDetail`, `DiscussionView`) carry more complexity than ideal — known tech debt.
- **No UI to reach an older review's findings/discussions.** Once a newer review succeeds, prior
  runs stay in the database but are not navigable in the UI. A read-only run-history entry point
  is a **post-MVP roadmap item** (it touches the read-only invariants, so it was not bundled
  into delivery).
- **Hybrid static-analysis + LLM review is deferred** — reviews are LLM-only.
- **Local-model reality:** quality and latency depend on the chosen Ollama model; a review and a
  discussion can contend for the model. There is no scheduler — both have timeouts and the UI
  shows honest waiting/error states.

### What I'd change for production

Manage schema with **Alembic** (not startup `ensure_schema`); add a **readiness** probe that
actually pings SQLite + the provider (today's `/api/health` is liveness-only); and if more than
one backend instance were ever needed, move review jobs to a **durable queue** with leases
instead of the single-process worker.

---

*This README and [`AI_USAGE.md`](./AI_USAGE.md) are self-contained — everything a reviewer needs
is in the tracked repository. Internal planning notes are intentionally not part of the
submission.*
