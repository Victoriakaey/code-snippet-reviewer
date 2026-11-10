"""Validation pipeline: turn an LLM's raw text into validated findings — or an honest
failure. This is the one genuinely PURE part of the review flow (no model, no network, no
DB), so it is fully unit-testable and deterministic.

LLM output is UNTRUSTED input. We parse defensively and distinguish four outcomes, which
must never be collapsed into each other (docs/ARCHITECTURE.md §5):

    raw output                         -> result
    {"findings": []}                   -> completed, 0 findings          (model found nothing)
    3 findings, 2 valid + 1 invalid    -> completed, 2 findings, 1 rejected
    3 findings, ALL invalid            -> failed (validation_error)      (bad model output)
    not JSON / no findings list        -> failed (invalid_response)      (malformed/structure)

Critically: a legitimately empty array is "no issues found" (a success), while every
finding being rejected is a quality failure — collapsing the second into the first would
report a broken review as a clean bill of health. A top-level structure error is also NOT
an empty-findings success.

Per-finding rules: severity/category in the enum, description non-empty, rationale non-empty
(the user-facing "why"), line_start >= 1, line_end >= line_start, and line_end <= the actual
snippet line count. Line numbers are NEVER clamped — forcing an out-of-range line onto a
real line would fabricate false evidence, so such a finding is dropped and counted instead.
Validation proves a finding is well-formed and in-range; it does NOT prove it is correct.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .models import CATEGORIES, SEVERITIES


@dataclass
class ValidatedReview:
    status: str  # "completed" | "failed"
    findings: list[dict] = field(default_factory=list)
    rejected_count: int = 0
    error_code: str | None = None  # "invalid_response" | "validation_error" | None
    error_message: str | None = None
    # Human-readable reasons for each dropped finding (for logs + the smoke report).
    rejections: list[str] = field(default_factory=list)


def _fail(code: str, message: str, rejected_count: int = 0,
          rejections: list[str] | None = None) -> ValidatedReview:
    return ValidatedReview(
        status="failed",
        error_code=code,
        error_message=message,
        rejected_count=rejected_count,
        rejections=rejections or [],
    )


def _validate_finding(entry: object, line_count: int) -> tuple[dict | None, str | None]:
    """Return (normalized_finding, None) if valid, else (None, reason)."""
    if not isinstance(entry, dict):
        return None, "finding is not an object"

    line_start = entry.get("line_start")
    line_end = entry.get("line_end")
    severity = entry.get("severity")
    category = entry.get("category")
    description = entry.get("description")
    rationale = entry.get("rationale")
    suggested_fix = entry.get("suggested_fix")

    if not isinstance(line_start, int) or isinstance(line_start, bool):
        return None, "line_start missing or not an integer"
    if not isinstance(line_end, int) or isinstance(line_end, bool):
        return None, "line_end missing or not an integer"
    if line_start < 1:
        return None, f"line_start {line_start} < 1"
    if line_end < line_start:
        return None, f"line_end {line_end} < line_start {line_start}"
    if line_end > line_count:
        return None, f"line_end {line_end} exceeds snippet length {line_count}"
    if severity not in SEVERITIES:
        return None, f"invalid severity {severity!r}"
    if category not in CATEGORIES:
        return None, f"invalid category {category!r}"
    if not isinstance(description, str) or not description.strip():
        return None, "description missing or empty"
    if not isinstance(rationale, str) or not rationale.strip():
        return None, "rationale missing or empty"
    if suggested_fix is not None and not isinstance(suggested_fix, str):
        return None, "suggested_fix is not a string"

    return {
        "line_start": line_start,
        "line_end": line_end,
        "severity": severity,
        "category": category,
        "description": description.strip(),
        "rationale": rationale.strip(),
        "suggested_fix": suggested_fix.strip() if isinstance(suggested_fix, str) and suggested_fix.strip() else None,
    }, None


def validate_review_output(raw_text: str, snippet_line_count: int) -> ValidatedReview:
    """Validate an LLM's raw review output against the snippet it was generated for."""
    try:
        data = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError):
        return _fail("invalid_response", "model output is not valid JSON")

    # Top-level structure error must NOT be read as an empty-findings success.
    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        return _fail(
            "invalid_response",
            "model output missing a top-level 'findings' array",
        )

    entries = data["findings"]
    if len(entries) == 0:
        # Legitimately empty: the model found nothing. This is a success.
        return ValidatedReview(status="completed", findings=[], rejected_count=0)

    valid: list[dict] = []
    rejections: list[str] = []
    for entry in entries:
        normalized, reason = _validate_finding(entry, snippet_line_count)
        if normalized is not None:
            valid.append(normalized)
        else:
            rejections.append(reason or "invalid finding")

    if not valid:
        # Non-empty array, but every finding was rejected -> quality failure, NOT "no issues".
        return _fail(
            "validation_error",
            f"all {len(entries)} finding(s) failed validation",
            rejected_count=len(rejections),
            rejections=rejections,
        )

    return ValidatedReview(
        status="completed",
        findings=valid,
        rejected_count=len(rejections),
        rejections=rejections,
    )
