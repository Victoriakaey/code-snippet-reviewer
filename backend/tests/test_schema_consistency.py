"""Schema-consistency guard: the three finding contracts must not drift apart.

The per-finding shape is declared in three places:
- FINDINGS_SCHEMA  (what we ask the model to emit),
- validate_review_output / _validate_finding  (what we accept),
- the Finding SQLAlchemy model  (what we persist).

A field rename or enum change in one place that isn't mirrored in the others would surface
as a silent bug during M3 persistence. These lightweight checks fail fast instead. We keep
the hand-written validator (clear + strict); this only pins the field/enum agreement.
"""
from __future__ import annotations

from app.models import CATEGORIES, SEVERITIES, Finding
from app.rubric import (
    FINDINGS_SCHEMA,
    OPTIONAL_FINDING_FIELDS,
    REQUIRED_FINDING_FIELDS,
    build_user_prompt,
)
from app.review_pipeline import validate_review_output

_ITEM = FINDINGS_SCHEMA["properties"]["findings"]["items"]


def test_schema_enums_match_model_enums():
    assert set(_ITEM["properties"]["severity"]["enum"]) == set(SEVERITIES)
    assert set(_ITEM["properties"]["category"]["enum"]) == set(CATEGORIES)


def test_schema_required_matches_declared_required_fields():
    assert set(_ITEM["required"]) == set(REQUIRED_FINDING_FIELDS)


def test_schema_properties_are_exactly_required_plus_optional():
    assert set(_ITEM["properties"]) == set(REQUIRED_FINDING_FIELDS) | set(
        OPTIONAL_FINDING_FIELDS
    )


def test_schema_forbids_extra_fields():
    assert _ITEM["additionalProperties"] is False
    assert FINDINGS_SCHEMA["additionalProperties"] is False


def test_finding_model_has_every_schema_field():
    columns = set(Finding.__table__.columns.keys())
    for field in (*REQUIRED_FINDING_FIELDS, *OPTIONAL_FINDING_FIELDS):
        assert field in columns, f"Finding model is missing column {field!r}"


def test_validator_enforces_each_required_field():
    # Dropping any required field must cause that finding to be rejected.
    line_count = 5
    base = {
        "line_start": 1,
        "line_end": 2,
        "description": "d",
        "rationale": "r",
        "category": "bug",
        "severity": "warning",
    }
    for field in REQUIRED_FINDING_FIELDS:
        entry = {k: v for k, v in base.items() if k != field}
        result = validate_review_output(
            '{"findings": [%s]}' % _as_json(entry), line_count
        )
        assert result.status == "failed", f"missing {field} should reject"
        assert result.error_code == "validation_error"


def _as_json(d: dict) -> str:
    import json

    return json.dumps(d)


def test_build_user_prompt_is_1_based_and_line_numbered():
    prompt = build_user_prompt("a\nb\nc", "python")
    assert "1: a" in prompt and "2: b" in prompt and "3: c" in prompt
