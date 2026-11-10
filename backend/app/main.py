"""FastAPI application entrypoint.

Wiring: CORS for the Vite dev server, a liveness health endpoint, the snippet router,
and the shared error envelope. Tables are created on startup via `create_all()` (MVP —
this does NOT migrate an existing schema; production would use Alembic).
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401 — registers ORM tables on Base before create_all.
from .config import settings
from .db import Base, engine, ensure_schema
from .errors import install_error_handlers
from .routers import findings, messages, reviews, rubric, snippets
from .worker import recover_interrupted_reviews, worker_loop

logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Create any missing tables on startup, then apply the additive column migration for any
    # pre-existing table (create_all does not alter existing tables). ensure_schema raises on
    # failure rather than starting with a missing column.
    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)
    # Startup recovery: fail any review left `running` by a previous crash (queued ones are
    # preserved). Single-process assumption — see app/worker.py.
    recovered = await asyncio.to_thread(recover_interrupted_reviews)
    if recovered:
        logger.info("startup recovery marked %d interrupted review(s) failed", recovered)

    # Start the single background review worker.
    stop_event = asyncio.Event()
    task = asyncio.create_task(worker_loop(stop_event))
    try:
        yield
    finally:
        # Clean shutdown: ask the loop to stop, then cancel if it's mid-await (e.g. a live
        # Ollama call). A review cancelled mid-run stays `running` and is recovered to
        # `failed` on the next startup.
        stop_event.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Code Snippet Reviewer API", version="0.1.0", lifespan=lifespan)

install_error_handlers(app)
app.include_router(snippets.router)
app.include_router(reviews.router)
app.include_router(findings.router)
app.include_router(messages.router)
app.include_router(rubric.router)

# The Vite dev server (and its preview server) call the API from a different origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    """Liveness probe ONLY: confirms the API process is up and can respond.

    It intentionally does NOT touch SQLite or Ollama, so a 200 here is not proof that
    the database or the model are reachable. A separate readiness check (pinging the DB
    and the configured provider) can be added later if deployment needs it.
    """
    return {"status": "ok", "llm_provider": settings.llm_provider}
