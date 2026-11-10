"""OpenAIProvider tests — injected fake SDK client only, NO billable API calls.

Covers the happy paths (review/discuss), every safe-failure branch (refusal, truncation, empty
body, SDK error, no choices), the request shape (strict json_schema, and NO `temperature`), the
OpenAI strict schema variant, and that the Ollama schema is left untouched.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from openai import OpenAIError

from app.providers import OpenAIProvider, ProviderError
from app.review_pipeline import validate_review_output
from app.rubric import FINDINGS_SCHEMA, OPENAI_FINDINGS_SCHEMA


def _run(coro):
    return asyncio.run(coro)


class _FakeCompletions:
    def __init__(self, outcome):
        self._outcome = outcome
        self.captured: dict = {}

    async def create(self, **kwargs):
        self.captured = kwargs
        o = self._outcome
        if isinstance(o, Exception):
            raise o
        if o.get("no_choices"):
            return SimpleNamespace(choices=[])
        message = SimpleNamespace(content=o.get("content"), refusal=o.get("refusal"))
        choice = SimpleNamespace(message=message, finish_reason=o.get("finish_reason", "stop"))
        return SimpleNamespace(choices=[choice])


class _FakeClient:
    def __init__(self, outcome):
        self.completions = _FakeCompletions(outcome)
        self.chat = SimpleNamespace(completions=self.completions)


def _provider(outcome, **kw):
    client = _FakeClient(outcome)
    p = OpenAIProvider(api_key="sk-not-used", model="gpt-5-mini", client=client, **kw)
    return p, client


FINDING = {"severity": "warning", "category": "bug", "line_start": 1, "line_end": 1,
           "description": "d", "rationale": "r", "suggested_fix": None}


# --- happy paths ---------------------------------------------------------------

def test_review_returns_raw_content_and_sends_strict_schema():
    p, client = _provider({"content": '{"findings": []}'})
    raw = _run(p.review(code="x = 1", language="python"))
    assert raw == '{"findings": []}'
    rf = client.completions.captured["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["schema"] is OPENAI_FINDINGS_SCHEMA
    # gpt-5 reasoning models reject temperature — we must never send it.
    assert "temperature" not in client.completions.captured


def test_discuss_returns_text_without_response_format():
    p, client = _provider({"content": "here is the answer"})
    out = _run(p.discuss(code="x=1", language="python", finding=FINDING, history=[], question="why?"))
    assert out == "here is the answer"
    assert "response_format" not in client.completions.captured  # free-text, not structured


def test_optional_params_passed_only_when_configured():
    p, client = _provider({"content": "{}"}, reasoning_effort="low", max_output_tokens=256)
    _run(p.review(code="x=1", language="python"))
    assert client.completions.captured["reasoning_effort"] == "low"
    assert client.completions.captured["max_completion_tokens"] == 256

    p2, client2 = _provider({"content": "{}"})
    _run(p2.review(code="x=1", language="python"))
    assert "reasoning_effort" not in client2.completions.captured
    assert "max_completion_tokens" not in client2.completions.captured


# --- safe failure branches (all -> ProviderError) ------------------------------

def test_refusal_raises_provider_error():
    p, _ = _provider({"content": None, "refusal": "I can't help with that."})
    with pytest.raises(ProviderError, match="refused"):
        _run(p.review(code="x=1", language="python"))


def test_truncated_response_raises_provider_error():
    p, _ = _provider({"content": '{"findings": [', "finish_reason": "length"})
    with pytest.raises(ProviderError, match="truncated"):
        _run(p.review(code="x=1", language="python"))


def test_empty_content_raises_provider_error():
    p, _ = _provider({"content": ""})
    with pytest.raises(ProviderError, match="empty"):
        _run(p.review(code="x=1", language="python"))


def test_no_choices_raises_provider_error():
    p, _ = _provider({"no_choices": True})
    with pytest.raises(ProviderError, match="no choices"):
        _run(p.review(code="x=1", language="python"))


def test_sdk_error_raises_provider_error():
    p, _ = _provider(OpenAIError("simulated rate limit / timeout / connection error"))
    with pytest.raises(ProviderError, match="OpenAI request failed"):
        _run(p.discuss(code="x=1", language="python", finding=FINDING, history=[], question="q"))


# --- schema variant + validation compatibility ---------------------------------

def test_openai_strict_schema_requires_all_fields_and_nullable_suggested_fix():
    item = OPENAI_FINDINGS_SCHEMA["properties"]["findings"]["items"]
    # strict: every property is required (incl. suggested_fix), and it is nullable.
    assert set(item["required"]) == set(item["properties"].keys())
    assert "suggested_fix" in item["required"]
    assert item["properties"]["suggested_fix"] == {"type": ["string", "null"]}
    assert item["additionalProperties"] is False
    assert OPENAI_FINDINGS_SCHEMA["additionalProperties"] is False


def test_ollama_schema_is_untouched():
    # The Ollama schema must NOT gain suggested_fix in required (its format allows omission).
    item = FINDINGS_SCHEMA["properties"]["findings"]["items"]
    assert "suggested_fix" not in item["required"]
    assert item["properties"]["suggested_fix"] == {"type": "string"}


def test_null_suggested_fix_passes_validation():
    raw = (
        '{"findings": [{"line_start": 1, "line_end": 1, "severity": "warning",'
        ' "category": "bug", "description": "d", "rationale": "r", "suggested_fix": null}]}'
    )
    result = validate_review_output(raw, snippet_line_count=1)
    assert result.status == "completed"
    assert len(result.findings) == 1
    assert result.findings[0]["suggested_fix"] is None
