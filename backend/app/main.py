"""FastAPI application entrypoint.

Wiring: CORS for the Vite dev server, a liveness health endpoint, the snippet router,
and the shared error envelope. Tables are created on startup via `create_all()` (MVP —
this does NOT migrate an existing schema; production would use Alembic).
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401 — registers ORM tables on Base before create_all.
from .config import settings
from .db import Base, engine
from .errors import install_error_handlers
from .routers import snippets


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Create any missing tables on startup (idempotent; no schema migration).
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Code Snippet Reviewer API", version="0.1.0", lifespan=lifespan)

install_error_handlers(app)
app.include_router(snippets.router)

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
