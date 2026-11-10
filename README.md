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
- **AI:** three providers behind one interface, selected via `LLM_PROVIDER` — `ollama` (local),
  `openai` (cloud), or `mock` (deterministic, no model); no automatic fallback between them

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

Then open http://localhost:5173 — it should show **"✓ Backend OK · provider: ollama"** (or
**`provider: mock`** when you run the backend with `LLM_PROVIDER=mock`).

## Configuration

Copy `backend/.env.example` to `backend/.env` and adjust. Key variables:

- `LLM_PROVIDER` — which review provider to use. No automatic fallback between providers.
  - `ollama` (default) — a real **local** model (private, offline, no API cost).
  - `openai` — a real **cloud** model via the OpenAI API (set `OPENAI_API_KEY`).
  - `mock` — a deterministic stand-in that needs no model; it exercises the full app flow
    but produces placeholder findings, **not** a real review.
- `OLLAMA_BASE_URL`, `OLLAMA_MODEL` — local model. Install Ollama and pull a code model,
  e.g. `ollama pull qwen2.5-coder:7b` (any local tag works; set `OLLAMA_MODEL` to match).
- `OPENAI_API_KEY`, `OPENAI_MODEL` — for the OpenAI provider. The key is read **only** from the
  environment / the gitignored `.env`, never hardcoded. `OPENAI_MODEL` defaults to `gpt-5-mini`;
  `OPENAI_REASONING_EFFORT` (minimal|low|medium|high) and `OPENAI_MAX_OUTPUT_TOKENS` are optional
  (we don't send `temperature` — gpt-5 reasoning models ignore it).
- `DATABASE_URL` — SQLite file path.

**Three ways to run the reviewer:** `mock` (no key, no model — easiest for a quick look),
`ollama` (real local model, no cloud account), or `openai` (real cloud model, needs an API key).

> No Ollama installed? Set `LLM_PROVIDER=mock` to run the app end-to-end with deterministic
> placeholder findings. Real AI review requires a local model via Ollama.

### Using OpenAI (`gpt-5-mini`) — real cloud reviews

The OpenAI provider is **fully implemented and has been validated against the live API**, not
just mocked. To switch from the local default to the cloud model, set three things in
`backend/.env` (the key is read only from the environment / this gitignored file — never
hardcoded, never logged):

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...        # your key; keep it out of source control and chat
OPENAI_MODEL=gpt-5-mini
```

**With Docker**, pass the key through from your host shell (the compose file already forwards
`OPENAI_API_KEY` and `OPENAI_MODEL`, and never bakes them into the image):

```bash
LLM_PROVIDER=openai OPENAI_API_KEY=sk-... docker compose up --build
```

(Without Docker, the same three variables in `backend/.env` are picked up by the backend.)

**Trade-offs — pick the provider per use, there is no automatic fallback:**

| | `ollama` (default) | `openai` / `gpt-5-mini` |
|---|---|---|
| **Privacy** | local, code never leaves the machine | code is sent to OpenAI |
| **Cost** | free | paid (~`$0.003` per review in testing) |
| **Latency** | ~6 s / review | ~18–35 s / review |
| **Quality** | weaker on hard cases | stronger true-bug detection |

**Model-quality limitations (measured, not assumed).** A small 8-case adversarial benchmark
(T1–T8, one run each, same snippets / rubric / prompt as the local model) showed `gpt-5-mini`
clearly better at **finding real bugs** — it correctly derived an average's off-by-one divisor,
explained a slice off-by-one, flagged SQL injection, and did **not** obey a prompt-injection
comment telling it to report nothing. But it also has a measurable **over-reporting tendency**:
on code that is actually clean it still emits findings, and will tag defensible edge-case
concerns (e.g. "this breaks for a generator / a non-integer argument") as `warning`/`bug` rather
than as a potential boundary limitation. Treat `gpt-5-mini` as **higher recall on real bugs, at
the cost of more false positives on clean code** — it rarely reports "no issues." Eight examples
are a qualitative signal, not a statistical claim. Provenance stored per review is the configured
model **alias** (`gpt-5-mini`), not the dated API build string the API returns.

> **Optional:** `backend/scripts/ollama_smoke.py` reviews three sample snippets against a
> running Ollama and prints findings, latency, and validation outcomes — a quick check that a
> local model responds in the expected shape (shape only, never semantic correctness).

## API

- `POST /api/snippets` — create a snippet (`title`, `language`, `code`) → `201`. Validation
  failures (empty title/code, unsupported language, oversized input) → `422`.
- `GET /api/snippets` — list snippets, newest first, each with a derived status and a
  review-run count (the dashboard's **Reviews** column).
- `GET /api/snippets/{id}` — one snippet, or `404`.
- `GET /api/snippets/{id}/reviews` — the snippet's review runs, newest first (id, run number,
  status, provider/model, finding count). Powers the UI's read-only **Review history** selector.
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
- **Every review run is navigable (read-only).** The snippet page has a **Review history** run
  selector; picking an older run shows that run's findings, its own provenance in **Review
  details**, and a read-only banner. A failed run shows its own status and sanitized error. The
  dashboard's **Reviews** column counts the runs. The backend enforces read-only regardless of
  the UI (older runs → `409`).
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
