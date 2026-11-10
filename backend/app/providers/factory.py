"""Explicit provider selection from LLM_PROVIDER — no silent fallback.

Only providers whose adapter is actually implemented are selectable:
- `ollama` — the real local review provider.
- `mock`   — deterministic stand-in for tests / running the app without Ollama.

`openai` is documented but NOT implemented in v1. Selecting it raises a clear ProviderError
at selection time, rather than failing with an obscure error deep inside a request.
"""
from __future__ import annotations

from ..config import Settings, settings as default_settings
from .base import ProviderError, ReviewProvider
from .mock import MockProvider
from .ollama import OllamaProvider


def get_provider(settings: Settings | None = None) -> ReviewProvider:
    cfg = settings or default_settings
    provider = cfg.llm_provider

    if provider == "ollama":
        return OllamaProvider(base_url=cfg.ollama_base_url, model=cfg.ollama_model)
    if provider == "mock":
        return MockProvider()
    if provider == "openai":
        raise ProviderError(
            "LLM_PROVIDER=openai is not implemented in this version. "
            "Use 'ollama' (local) or 'mock'."
        )
    raise ProviderError(f"unknown LLM_PROVIDER: {provider!r}")
