"""Explicit provider selection from LLM_PROVIDER — no silent fallback.

Selectable providers (each with an implemented adapter):
- `ollama` — the real local review provider.
- `openai` — a real cloud provider via the OpenAI SDK (requires OPENAI_API_KEY).
- `mock`   — deterministic stand-in for tests / running the app without any model.

An unconfigured or unknown provider raises a clear ProviderError at selection time, rather
than failing with an obscure error deep inside a request.
"""
from __future__ import annotations

from ..config import Settings, settings as default_settings
from .base import ProviderError, ReviewProvider
from .mock import MockProvider
from .ollama import OllamaProvider
from .openai import OpenAIProvider


def get_provider(settings: Settings | None = None) -> ReviewProvider:
    cfg = settings or default_settings
    provider = cfg.llm_provider

    if provider == "ollama":
        return OllamaProvider(
            base_url=cfg.ollama_base_url,
            model=cfg.ollama_model,
            timeout=cfg.ollama_timeout,
        )
    if provider == "mock":
        return MockProvider()
    if provider == "openai":
        if not cfg.openai_api_key:
            raise ProviderError(
                "LLM_PROVIDER=openai requires OPENAI_API_KEY to be set in the environment."
            )
        return OpenAIProvider(
            api_key=cfg.openai_api_key,
            model=cfg.openai_model,
            timeout=cfg.openai_timeout,
            reasoning_effort=cfg.openai_reasoning_effort,
            max_output_tokens=cfg.openai_max_output_tokens,
        )
    raise ProviderError(f"unknown LLM_PROVIDER: {provider!r}")
