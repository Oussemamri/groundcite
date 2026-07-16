"""FastAPI application entrypoint (spec §9).

AD-1: ``build_services(get_settings())`` runs ONCE in the lifespan startup and
is stored on ``app.state.services``; ``deps.get_services`` returns it. Lazy
adapters mean startup is fast; the first ask pays the model load.

AD-6: RFC-7807 ``application/problem+json`` exception handlers.
AD-9: structlog JSON to stdout; a request-id middleware binds one id per request.

Run locally with:  ``uvicorn app.main:app --reload`` (spec §4.1 dev shape).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.errors import install_exception_handlers
from app.logging_conf import configure_logging, get_logger
from app.routes.asks import router as asks_router
from app.routes.documents import router as documents_router
from app.routes.evals import router as evals_router
from app.routes.health import router as health_router
from groundcite.config import get_settings
from groundcite.container import build_services


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build services once at startup (AD-1), release at shutdown."""
    configure_logging()
    log = get_logger("app.startup")
    settings = get_settings()
    app.state.services = build_services(settings)
    log.info("services_built", tau_retrieval=settings.tau_retrieval, groq_model=settings.groq_model)
    yield
    app.state.services = None


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Bind a per-request id into structlog contextvars (AD-9)."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        import structlog

        request_id = request.headers.get("x-request-id") or str(uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response


def create_app() -> FastAPI:
    """Build the GroundCite API (spec §9)."""
    app = FastAPI(
        title="GroundCite API",
        version="0.1.0",
        summary="Grounded Q&A over aerospace & engineering standards (spec §9).",
        lifespan=lifespan,
    )
    app.add_middleware(RequestIdMiddleware)
    install_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(documents_router)
    app.include_router(asks_router)
    app.include_router(evals_router)
    # POST /asks (SSE ask stream) and the write routes (jobs) land in Phase 3/4.
    return app


app = create_app()
