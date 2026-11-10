"""Review-quality probe (manual) — contrasting cases to calibrate the rubric, NOT a pass/fail
gate. It checks the reviewer's JUDGMENT, which is non-deterministic, so read the actual
output; do not assert exact findings.

Run against a live Ollama with a code model:

    cd backend
    OLLAMA_MODEL=qwen2.5-coder:7b-instruct-q4_K_M .venv/bin/python scripts/review_quality_probe.py

Each case states a REASONABLE expectation (a range, not a single right answer):
- one-line style        : 0 findings is acceptable; an info/maintainability note is also fine.
- mutable default arg   : should flag a real bug.
- divide, no context    : may hint at divide-by-zero, must NOT assert it definitely crashes.
- hardcoded credential  : should flag a security risk.
- clean conventional fn : should be allowed to return 0 findings (no invented problems).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.providers import OllamaProvider, ProviderError  # noqa: E402
from app.review_pipeline import validate_review_output  # noqa: E402
from app.rubric import PROMPT_VERSION, RUBRIC_VERSION  # noqa: E402

CASES: list[tuple[str, str]] = [
    ("one-line style", "def f(): return 1\n"),
    (
        "mutable default argument (real bug)",
        "def add_item(item, items=[]):\n    items.append(item)\n    return items\n",
    ),
    ("divide, no context", "def divide(a, b):\n    return a / b\n"),
    (
        "hardcoded credential (security)",
        # Synthetic test input — NOT a real secret. A fake key the probe feeds the model to
        # check whether it flags a hardcoded credential.
        'API_KEY = "sk-live-abc123"\n\n\ndef call():\n    return API_KEY\n',
    ),
    ("clean conventional function", "def add(a, b):\n    return a + b\n"),
]


async def run_case(provider: OllamaProvider, title: str, code: str) -> None:
    line_count = len(code.splitlines())
    print("=" * 78)
    print(f"CASE: {title}")
    for i, line in enumerate(code.splitlines(), 1):
        print(f"   {i}  {line}")
    print("-" * 78)
    try:
        raw = await provider.review(code=code, language="python")
    except ProviderError as exc:
        print(f"PROVIDER ERROR: {exc}")
        return
    result = validate_review_output(raw, line_count)
    print(f"status: {result.status}   accepted: {len(result.findings)}   "
          f"rejected: {result.rejected_count}")
    for f in result.findings:
        print(f"  [{f['severity']}/{f['category']}] L{f['line_start']}-{f['line_end']}: "
              f"{f['description']}")
    for r in result.rejections:
        print(f"  REJECTED: {r}")


async def main() -> None:
    provider = OllamaProvider(base_url=settings.ollama_base_url, model=settings.ollama_model)
    print(f"model: {provider.model_name}   rubric: {RUBRIC_VERSION}   prompt: {PROMPT_VERSION}")
    for title, code in CASES:
        await run_case(provider, title, code)
    print("=" * 78)


if __name__ == "__main__":
    asyncio.run(main())
