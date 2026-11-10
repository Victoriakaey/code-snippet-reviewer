"""Deterministic mock provider — same input always yields the same raw output.

Used by the test suite and as a no-Ollama way to exercise the full app flow (the UI, job
machinery, persistence) without a real model. Its findings are produced by trivial pattern
rules, NOT by any understanding of the code — it is never a real review, only a stable,
schema-conformant stand-in. The output is raw JSON text, exactly like a real provider's, so
it flows through the same validation pipeline.
"""
from __future__ import annotations

import json

from .base import ReviewProvider


class MockProvider(ReviewProvider):
    name = "mock"
    model_name = "mock-deterministic"

    async def review(self, *, code: str, language: str) -> str:
        lines = code.splitlines()
        findings: list[dict] = []

        # Deterministic pattern rules (line numbers kept in range).
        lowered = code.lower()
        if "eval(" in code or "exec(" in code:
            idx = next(
                (i for i, ln in enumerate(lines, start=1) if "eval(" in ln or "exec(" in ln),
                1,
            )
            findings.append(
                {
                    "line_start": idx,
                    "line_end": idx,
                    "description": "Use of eval/exec on dynamic input.",
                    "rationale": "Executing dynamically built code can run arbitrary "
                    "commands if any input reaches it; this is a common injection vector.",
                    "suggested_fix": "Parse or dispatch explicitly instead of eval/exec.",
                    "category": "security",
                    "severity": "critical",
                }
            )
        if "password" in lowered or "secret" in lowered or "api_key" in lowered:
            idx = next(
                (
                    i
                    for i, ln in enumerate(lines, start=1)
                    if any(k in ln.lower() for k in ("password", "secret", "api_key"))
                ),
                1,
            )
            findings.append(
                {
                    "line_start": idx,
                    "line_end": idx,
                    "description": "Possible hardcoded credential.",
                    "rationale": "A secret committed in source can leak through version "
                    "control and cannot be rotated without a code change.",
                    "suggested_fix": "Load it from an environment variable or secret store.",
                    "category": "security",
                    "severity": "warning",
                }
            )

        # Always emit one low-severity maintainability note so the flow has a finding.
        findings.append(
            {
                "line_start": 1,
                "line_end": 1,
                "description": "Snippet reviewed by the mock provider (placeholder finding).",
                "rationale": "The mock provider emits a deterministic note so the review "
                "flow can be exercised without a real model; it is not a real issue.",
                "suggested_fix": None,
                "category": "maintainability",
                "severity": "info",
            }
        )

        # NOTE: we deliberately do NOT clamp line numbers here. The validation pipeline's
        # contract is that out-of-range lines are rejected, never clamped (clamping would
        # fabricate evidence). A provider must not silently sanitize its own output, or it
        # would hide the very case the validator exists to catch. The findings above are
        # already in range by construction (line 1, or a matched line index).
        return json.dumps({"findings": findings})

    async def discuss(
        self, *, code: str, language: str, finding: dict, history: list[dict], question: str
    ) -> str:
        # Deterministic canned reply that echoes the finding — not a real answer.
        return (
            f"(mock discussion) Regarding the {finding.get('severity')} "
            f"{finding.get('category')} finding on lines {finding.get('line_start')}-"
            f"{finding.get('line_end')}: this is a deterministic mock reply, not real "
            f"analysis. You asked: {question.strip()}"
        )
