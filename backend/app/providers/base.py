"""Provider interface.

`review()` is async on purpose: the M3 worker will call a provider from within the event
loop, and model inference can take seconds. A synchronous network call there would block
FastAPI's loop, so the contract is async from the start (a sync-only SDK must be isolated in
the implementation, not exposed here).

Note: a review call is NOT a pure function — model output, latency, and network state all
vary. Only the downstream validation (`app.review_pipeline`) is pure.

Reserved for M6 (not implemented here, to avoid an unused placeholder): a `discuss()` method
with the intended contract
    async def discuss(*, code: str, language: str, finding: dict,
                      history: list[dict], question: str) -> str
— one quick, timeout-bounded LLM call answering a follow-up about a specific finding. It is
intentionally absent from this interface until M6 builds it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class ProviderError(Exception):
    """A provider could not produce output (network error, timeout, bad HTTP status,
    unselected/unsupported provider). The raw model text, when one exists, is validated
    separately — this is for the call itself failing."""


class ReviewProvider(ABC):
    """Produces a raw (unvalidated) review of one code snippet.

    Subclasses set `name` (stored in `reviews.provider`) and `model_name` (stored in
    `reviews.model_name`) for provenance.
    """

    name: str
    model_name: str

    @abstractmethod
    async def review(self, *, code: str, language: str) -> str:
        """Return the model's RAW text output (expected to be JSON). Raise ProviderError
        if the call itself fails. Does NOT validate — that is the pipeline's job."""
        raise NotImplementedError
