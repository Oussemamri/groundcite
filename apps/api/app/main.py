"""FastAPI application entrypoint (spec §9).

Run locally with:  uvicorn app.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI

from app.routes.health import router as health_router


def create_app() -> FastAPI:
    """Build the GroundCite API. Only ``/healthz`` is wired in the P5 skeleton."""
    app = FastAPI(
        title="GroundCite API",
        version="0.1.0",
        summary="Grounded Q&A over aerospace & engineering standards (spec §9).",
    )
    app.include_router(health_router)
    # /api/v1 routers (asks, documents, chunks, eval) are added in Week 4.
    return app


app = create_app()
