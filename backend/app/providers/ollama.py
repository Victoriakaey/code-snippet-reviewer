"""Ollama provider — a local code model via Ollama's /api/chat with structured output.

We pass the rubric JSON schema in `format`, so Ollama constrains the model to emit JSON
matching it (Ollama structured outputs). The backend still re-validates every field — a
schema-conformant response proves structure, not correctness.

No silent fallback: if the call fails (timeout, connection error, bad status) we raise
ProviderError; if the returned text is not valid/conformant JSON, the validation pipeline
reports a `failed` review. We never retry in a different mode to paper over a bad response —
failures stay observable.
"""
from __future__ import annotations

import httpx

from ..rubric import FINDINGS_SCHEMA, SYSTEM_PROMPT, build_user_prompt
from .base import ProviderError, ReviewProvider


class OllamaProvider(ReviewProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model
        self.timeout = timeout

    async def review(self, *, code: str, language: str) -> str:
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(code, language)},
            ],
            "format": FINDINGS_SCHEMA,
            "stream": False,
            # Low temperature for more reproducible structured output.
            "options": {"temperature": 0},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderError(f"Ollama request timed out after {self.timeout}s") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Ollama request failed: {exc}") from exc

        if response.status_code != 200:
            raise ProviderError(
                f"Ollama returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            body = response.json()
            return body["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderError(f"unexpected Ollama response shape: {exc}") from exc
