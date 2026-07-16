"""RFC-7807 problem+json contract for the API (spec §9, AD-6).

Errors are emitted as ``application/problem+json``. ``type`` URIs are stable
(``https://groundcite.dev/problems/<slug>`` — they need not resolve). Handlers
remap FastAPI's default 422 and translate domain-facing exceptions raised by
routes into the right status. No stack traces in bodies (AD-6).
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.logging_conf import get_logger

_PROBLEM_TYPE_BASE = "https://groundcite.dev/problems"


class Problem(BaseModel):
    """RFC-7807 problem document."""

    model_config = ConfigDict(extra="forbid")

    type: str
    title: str
    status: int
    detail: str | None = None
    instance: str = Field(default_factory=lambda: str(uuid4()))


# --- domain-facing exceptions routes raise (mapped to status by handlers) ---


class NotFoundError(Exception):
    """A referenced slug/id does not exist → 404."""

    def __init__(self, slug: str, label: str = "resource") -> None:
        self.slug = slug
        self.label = label
        super().__init__(f"{label} not found: {slug}")


class UnhealthyError(Exception):
    """A /healthz check failed → 503. ``detail`` carries per-check status."""

    def __init__(self, checks: dict[str, str]) -> None:
        self.checks = checks
        super().__init__("health check failed")


def _problem(
    status: int,
    type_slug: str,
    title: str,
    detail: str | None,
) -> Problem:
    return Problem(
        type=f"{_PROBLEM_TYPE_BASE}/{type_slug}",
        title=title,
        status=status,
        detail=detail,
    )


def _problem_response(problem: Problem) -> JSONResponse:
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(mode="json"),
        media_type="application/problem+json",
    )


def install_exception_handlers(app: FastAPI) -> None:
    """Register RFC-7807 handlers on ``app`` (AD-6)."""

    @app.exception_handler(NotFoundError)
    async def _not_found(_request: Request, exc: NotFoundError) -> JSONResponse:
        return _problem_response(
            _problem(
                status=404,
                type_slug="not-found",
                title="Not Found",
                detail=str(exc),
            )
        )

    @app.exception_handler(UnhealthyError)
    async def _unhealthy(_request: Request, exc: UnhealthyError) -> JSONResponse:
        detail = "; ".join(f"{k}: {v}" for k, v in exc.checks.items())
        return _problem_response(
            _problem(
                status=503,
                type_slug="unhealthy",
                title="Service Unavailable",
                detail=detail or None,
            )
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return _problem_response(
            _problem(
                status=422,
                type_slug="validation-error",
                title="Validation Error",
                detail=str(exc.errors()),
            )
        )

    @app.exception_handler(Exception)
    async def _fallback(_request: Request, exc: Exception) -> JSONResponse:
        # No stack trace in the body (AD-6). The exception message is not
        # surfaced to clients (could leak internals); it is logged instead.
        get_logger("app.errors").exception("unhandled_exception", error=str(exc))
        return _problem_response(
            _problem(
                status=500,
                type_slug="internal-error",
                title="Internal Server Error",
                detail=None,
            )
        )


def not_found_or_raise[T](value: T | None, slug: str, label: str = "document") -> T:
    """Return ``value`` or raise NotFoundError(404) — used by read routes."""
    if value is None:
        raise NotFoundError(slug=slug, label=label)
    return value


def coerce_id(value: str, label: str = "id") -> UUID:
    """Parse a path id to UUID or raise NotFoundError (a malformed id is a 404,
    not a 422 — it identifies no resource)."""
    try:
        return UUID(value)
    except ValueError as exc:
        raise NotFoundError(slug=value, label=label) from exc
