"""FastAPI application entrypoint.

M0 scope: app wiring, CORS for the Vite dev server, and a health endpoint. Real
routers (snippets / reviews / findings) are added from M1 onward.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings

app = FastAPI(title="Code Snippet Reviewer API", version="0.1.0")

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
