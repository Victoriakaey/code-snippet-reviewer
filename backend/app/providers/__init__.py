"""LLM review providers (M2).

`ReviewProvider.review()` returns the model's RAW text — validation lives separately in
`app.review_pipeline` (the pure part). Selection is explicit via `LLM_PROVIDER`, with no
silent fallback between providers.
"""
from .base import ProviderError, ReviewProvider
from .factory import get_provider
from .mock import MockProvider
from .ollama import OllamaProvider

__all__ = [
    "ProviderError",
    "ReviewProvider",
    "MockProvider",
    "OllamaProvider",
    "get_provider",
]
