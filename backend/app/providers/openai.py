"""OpenAI provider — a cloud code model via the official `openai` SDK (AsyncOpenAI).

Mirrors OllamaProvider: `review()` asks for JSON matching the rubric schema (OpenAI *strict*
structured outputs, which require every property in `required` + nullable optionals — see
`OPENAI_FINDINGS_SCHEMA`); `discuss()` is a free-text answer. The backend still re-validates
every field (`app.review_pipeline`) — a schema-conformant response proves structure, not truth.

No silent fallback: any call failure (timeout, rate limit, connection, bad status, a model
*refusal*, a truncated response, or an empty body) raises `ProviderError`, which the worker
turns into a `failed` review and the discuss endpoint into a retryable 503. We never retry in
a different provider/mode to paper over a bad response.

Parameters: we deliberately do NOT send `temperature` — gpt-5-family reasoning models reject or
ignore it. Generation is tuned via an optional `reasoning_effort` and an optional output-token
cap (`max_completion_tokens`), both passed only when configured.
"""
from __future__ import annotations

from openai import AsyncOpenAI, OpenAIError

from ..rubric import (
    OPENAI_FINDINGS_SCHEMA,
    SYSTEM_PROMPT,
    build_discuss_prompt,
    build_user_prompt,
)
from .base import ProviderError, ReviewProvider

_REVIEW_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "code_review_findings",
        "strict": True,
        "schema": OPENAI_FINDINGS_SCHEMA,
    },
}


class OpenAIProvider(ReviewProvider):
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        reasoning_effort: str | None = None,
        max_output_tokens: int | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.model_name = model
        self.timeout = timeout
        self._reasoning_effort = reasoning_effort
        self._max_output_tokens = max_output_tokens
        # Injected client lets tests exercise every branch without a billable call; production
        # builds a real AsyncOpenAI bound to the configured key + timeout.
        self._client = client or AsyncOpenAI(api_key=api_key, timeout=timeout)

    async def _create(self, messages: list[dict], response_format: dict | None = None) -> str:
        kwargs: dict = {"model": self.model_name, "messages": messages}
        if response_format is not None:
            kwargs["response_format"] = response_format
        if self._reasoning_effort:
            kwargs["reasoning_effort"] = self._reasoning_effort
        if self._max_output_tokens:
            kwargs["max_completion_tokens"] = self._max_output_tokens

        try:
            resp = await self._client.chat.completions.create(**kwargs)
        except OpenAIError as exc:  # timeout / rate limit / connection / bad status, all here
            raise ProviderError(f"OpenAI request failed: {exc}") from exc

        if not getattr(resp, "choices", None):
            raise ProviderError("OpenAI returned no choices")
        choice = resp.choices[0]
        message = choice.message

        # A model refusal (safety) in structured mode comes back as `message.refusal`, not JSON.
        if getattr(message, "refusal", None):
            raise ProviderError(f"OpenAI refused the request: {message.refusal}")
        # A truncated response would be invalid/partial JSON — fail clearly rather than feed the
        # validator a half object.
        if getattr(choice, "finish_reason", None) == "length":
            raise ProviderError("OpenAI response was truncated (raise the output-token limit)")

        content = message.content
        if not content:
            raise ProviderError("OpenAI returned an empty response")
        return content

    async def review(self, *, code: str, language: str) -> str:
        return await self._create(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(code, language)},
            ],
            response_format=_REVIEW_RESPONSE_FORMAT,
        )

    async def discuss(
        self, *, code: str, language: str, finding: dict, history: list[dict], question: str
    ) -> str:
        # Free-text answer (no structured-output schema).
        return await self._create(build_discuss_prompt(code, language, finding, history, question))
