"""Validation pipeline tests — the four outcomes must stay distinct, and each per-finding
rule must actually reject.
"""
from __future__ import annotations

import json

import pytest

from app.review_pipeline import validate_review_output

LINE_COUNT = 10


def _finding(**overrides) -> dict:
    base = {
        "line_start": 1,
        "line_end": 2,
        "description": "off-by-one in loop bound",
        "rationale": "the loop runs one iteration too many, indexing past the array end",
        "suggested_fix": "use < instead of <=",
        "category": "bug",
        "severity": "warning",
    }
    base.update(overrides)
    return base


def _raw(findings: list[dict]) -> str:
    return json.dumps({"findings": findings})


# --- The four top-level outcomes -------------------------------------------------


def test_empty_array_is_completed_zero_findings():
    result = validate_review_output(_raw([]), LINE_COUNT)
    assert result.status == "completed"
    assert result.findings == []
    assert result.rejected_count == 0
    assert result.error_code is None


def test_some_valid_some_invalid_is_completed_with_rejected_count():
    result = validate_review_output(
        _raw([_finding(), _finding(severity="fatal")]), LINE_COUNT
    )
    assert result.status == "completed"
    assert len(result.findings) == 1
    assert result.rejected_count == 1
    assert result.error_code is None


def test_all_invalid_nonempty_is_failed_validation_error():
    result = validate_review_output(
        _raw([_finding(severity="fatal"), _finding(category="typo")]), LINE_COUNT
    )
    assert result.status == "failed"
    assert result.error_code == "validation_error"
    assert result.rejected_count == 2
    assert result.findings == []


def test_malformed_json_is_failed_invalid_response():
    result = validate_review_output("not json {", LINE_COUNT)
    assert result.status == "failed"
    assert result.error_code == "invalid_response"


def test_top_level_structure_error_is_not_empty_findings():
    # A dict without a 'findings' list must FAIL, never be read as zero findings.
    result = validate_review_output(json.dumps({"issues": []}), LINE_COUNT)
    assert result.status == "failed"
    assert result.error_code == "invalid_response"


def test_findings_not_a_list_is_failed():
    result = validate_review_output(json.dumps({"findings": "none"}), LINE_COUNT)
    assert result.status == "failed"
    assert result.error_code == "invalid_response"


# --- Per-finding rejection rules -------------------------------------------------


@pytest.mark.parametrize(
    "overrides,reason_substr",
    [
        ({"severity": "fatal"}, "severity"),
        ({"category": "typo"}, "category"),
        ({"line_start": 0}, "line_start 0"),
        ({"line_start": 5, "line_end": 3}, "line_end 3 < line_start 5"),
        ({"line_end": LINE_COUNT + 1}, "exceeds snippet length"),
        ({"description": "   "}, "description"),
        ({"rationale": ""}, "rationale"),
        ({"line_start": "1"}, "line_start missing or not an integer"),
        ({"line_end": None}, "line_end missing or not an integer"),
    ],
)
def test_single_rule_rejects(overrides, reason_substr):
    # One bad finding among otherwise-valid ones -> dropped + counted, review still completed.
    result = validate_review_output(
        _raw([_finding(), _finding(**overrides)]), LINE_COUNT
    )
    assert result.status == "completed"
    assert len(result.findings) == 1
    assert result.rejected_count == 1
    assert any(reason_substr in r for r in result.rejections)


def test_missing_required_field_rejected():
    bad = _finding()
    del bad["rationale"]
    result = validate_review_output(_raw([_finding(), bad]), LINE_COUNT)
    assert result.rejected_count == 1
    assert len(result.findings) == 1


def test_boolean_is_not_accepted_as_line_number():
    # bool is a subclass of int in Python; the validator must reject it.
    result = validate_review_output(_raw([_finding(line_start=True)]), LINE_COUNT)
    assert result.status == "failed"
    assert result.error_code == "validation_error"


def test_optional_suggested_fix_may_be_absent():
    f = _finding()
    del f["suggested_fix"]
    result = validate_review_output(_raw([f]), LINE_COUNT)
    assert result.status == "completed"
    assert len(result.findings) == 1
    assert result.findings[0]["suggested_fix"] is None


def test_valid_finding_is_normalized_and_trimmed():
    result = validate_review_output(
        _raw([_finding(description="  trailing space  ")]), LINE_COUNT
    )
    assert result.findings[0]["description"] == "trailing space"
