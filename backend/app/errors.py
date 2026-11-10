"""Consistent, sanitized error envelope: `{"error": {"code", "message"}}`.

Both FastAPI's own validation errors (422) and raised HTTPExceptions (e.g. 404) are
reshaped into this single envelope so every client sees one error shape. Messages are
kept to validation text / explicit HTTPException details — never raw exception internals.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

_CODE_BY_STATUS = {
    400: "bad_request",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
}


def _code_for(status_code: int) -> str:
    return _CODE_BY_STATUS.get(status_code, "error")


def _summarize_validation(errors: list[dict]) -> str:
    """One readable line from Pydantic's error list, e.g. 'code: must not be empty'."""
    parts = []
    for err in errors:
        loc = [str(p) for p in err.get("loc", ()) if p not in ("body",)]
        field = ".".join(loc) if loc else "request"
        parts.append(f"{field}: {err.get('msg', 'invalid')}")
    return "; ".join(parts) or "invalid request"


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(_request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": _code_for(exc.status_code), "message": exc.detail}},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(_request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": _summarize_validation(exc.errors()),
                }
            },
        )
