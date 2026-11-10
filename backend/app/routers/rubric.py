"""GET /api/rubric — the static, versioned rubric for the Review Details drawer.

Returns the CURRENT rubric. A historical review may have run under a different
`rubric_version`; the UI compares a review's stored `rubric_version` to this one and must
not present the current rubric as the one that produced an older review.
"""
from __future__ import annotations

from fastapi import APIRouter

from ..rubric import (
    PROMPT_VERSION,
    RUBRIC_DIMENSIONS,
    RUBRIC_NAME,
    RUBRIC_SEVERITIES,
    RUBRIC_VERSION,
)
from ..schemas import RubricResponse

router = APIRouter(prefix="/api", tags=["rubric"])


@router.get("/rubric", response_model=RubricResponse)
def get_rubric() -> RubricResponse:
    return RubricResponse(
        name=RUBRIC_NAME,
        rubric_version=RUBRIC_VERSION,
        prompt_version=PROMPT_VERSION,
        dimensions=RUBRIC_DIMENSIONS,
        severities=RUBRIC_SEVERITIES,
    )
