"""FastAPI dependencies (spec §9, AD-1).

Services are a process-wide singleton built ONCE in the app lifespan (AD-1):
the reranker/embedder adapters lazy-load ~2GB of models — per-request
construction (the P5 skeleton) would reload them per call. ``get_services``
returns the singleton from ``app.state.services``. Routes should never construct
services or import adapters (spec §4 dependency rule).
"""

from __future__ import annotations

from fastapi import Request

from app.jobs import JobRegistry
from groundcite.config import Settings, get_settings
from groundcite.container import Services


def get_app_settings() -> Settings:
    """Live settings (resolves the ``.env``-backed config, spec §11)."""
    return get_settings()


def get_services(request: Request) -> Services:
    """Return the process-wide Services singleton (AD-1).

    Built in ``main.create_app``'s lifespan startup and stored on
    ``app.state.services``. Unit tests replace this dependency via
    ``app.dependency_overrides`` (AD-7); the live TestClient / ``uvicorn`` path
    runs the lifespan so the singleton exists.
    """
    services: Services | None = getattr(request.app.state, "services", None)
    if services is None:  # pragma: no cover - lifespan always runs under uvicorn/TestClient
        raise RuntimeError(
            "app.state.services is unset — the lifespan startup did not run. "
            "Use TestClient (runs lifespan) or dependency_overrides (AD-7)."
        )
    return services


def get_jobs(request: Request) -> JobRegistry:
    """Return the process-wide JobRegistry singleton (AD-5)."""
    jobs: JobRegistry | None = getattr(request.app.state, "jobs", None)
    if jobs is None:  # pragma: no cover - lifespan always runs under uvicorn/TestClient
        raise RuntimeError(
            "app.state.jobs is unset — the lifespan startup did not run. "
            "Use TestClient (runs lifespan) or dependency_overrides (AD-7)."
        )
    return jobs
