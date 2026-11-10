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

from ..rubric import (
    FINDINGS_SCHEMA,
    SYSTEM_PROMPT,
    build_discuss_prompt,
    build_user_prompt,
)
from .base import ProviderError, ReviewProvider


class OllamaProvider(ReviewProvider):
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model
        self.timeout = timeout
        # Optional transport injection — lets tests drive the error branches with
        # httpx.MockTransport without a live server. Production leaves it None.
        self._transport = transport

    async def _chat(self, messages: list[dict], fmt: dict | None = None) -> str:
        payload: dict = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0},
        }
        if fmt is not None:
            payload["format"] = fmt
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, transport=self._transport
            ) as client:
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
            return response.json()["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderError(f"unexpected Ollama response shape: {exc}") from exc

    async def review(self, *, code: str, language: str) -> str:
        return await self._chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(code, language)},
            ],
            fmt=FINDINGS_SCHEMA,
        )

    async def discuss(
        self, *, code: str, language: str, finding: dict, history: list[dict], question: str
    ) -> str:
        # Free-text answer (no structured-output schema).
        return await self._chat(
            build_discuss_prompt(code, language, finding, history, question)
        )
