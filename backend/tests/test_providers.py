"""Provider tests: mock determinism, mock output validity, and factory selection."""
from __future__ import annotations

import asyncio

import pytest

from app.config import Settings
from app.providers import MockProvider, OllamaProvider, ProviderError, get_provider
from app.review_pipeline import validate_review_output


def _run(coro):
    return asyncio.run(coro)


# --- MockProvider ---------------------------------------------------------------


def test_mock_is_deterministic():
    code = "def f(x):\n    return eval(x)\n"
    out1 = _run(MockProvider().review(code=code, language="python"))
    out2 = _run(MockProvider().review(code=code, language="python"))
    assert out1 == out2


def test_mock_output_passes_validation():
    code = "password = '123'\nprint(password)\n"
    raw = _run(MockProvider().review(code=code, language="python"))
    result = validate_review_output(raw, snippet_line_count=len(code.splitlines()))
    assert result.status == "completed"
    assert len(result.findings) >= 1
    # The security pattern (hardcoded credential) should be present.
    assert any(f["category"] == "security" for f in result.findings)


def test_mock_line_refs_stay_in_range():
    code = "x = 1\n"  # single line
    raw = _run(MockProvider().review(code=code, language="python"))
    result = validate_review_output(raw, snippet_line_count=1)
    assert result.status == "completed"
    for f in result.findings:
        assert 1 <= f["line_start"] <= 1
        assert f["line_end"] <= 1


# --- Factory selection ----------------------------------------------------------


def test_factory_selects_ollama():
    cfg = Settings(llm_provider="ollama")
    provider = get_provider(cfg)
    assert isinstance(provider, OllamaProvider)
    assert provider.name == "ollama"


def test_factory_selects_mock():
    cfg = Settings(llm_provider="mock")
    assert isinstance(get_provider(cfg), MockProvider)


def test_factory_rejects_unimplemented_openai():
    cfg = Settings(llm_provider="openai")
    with pytest.raises(ProviderError, match="not implemented"):
        get_provider(cfg)


def test_factory_rejects_unknown_provider():
    cfg = Settings(llm_provider="banana")
    with pytest.raises(ProviderError, match="unknown"):
        get_provider(cfg)
