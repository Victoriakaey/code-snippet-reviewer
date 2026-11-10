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
    """Liveness probe. Reports the configured LLM provider (no secrets)."""
    return {"status": "ok", "llm_provider": settings.llm_provider}
