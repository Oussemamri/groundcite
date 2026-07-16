"""Health route (spec §9 GET /healthz, spec §12, AD-9).

Extends the P5 static ``{"status": "ok"}`` to: DB liveness (via the live
LibraryService.list_documents — the real repository round-trip the app uses)
plus the running config's ``tau_retrieval`` and ``groq_model`` (WEEK4 residual
#4: drift visible from one request — those two are the ones that silently
invalidated Week 3's re-runs). Any DB check failing → 503 problem+json with
per-check detail (AD-6).

Deviation from AD-9's literal "provider (Groq GET /models)" (stated plainly, not
worked around silently): a live provider ping requires a new ``ping()`` seam
across the LLMProvider port + its adapters + a service accessor — core surface
that WEEK4 §0.4 keeps out of the interface-only scope. The demo-grade /healthz
still satisfies the explicitly-scoped residual #4 deliverable (config drift
visible from one request) and reports provider configuration without a live
probe. A real provider ping is flagged for the next owner as a spec §12
observability extension (see docs/WEEK4_RESULTS.md).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_app_settings, get_services
from app.errors import UnhealthyError
from app.models import _Out
from groundcite.config import Settings
from groundcite.container import Services


class HealthOut(_Out):
    status: str
    checks: dict[str, str]
    config: dict[str, object]


router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthOut)
def healthz(
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_app_settings),
) -> HealthOut:
    checks: dict[str, str] = {"db": "ok"}
    try:
        services.library.list_documents()  # real repository round-trip
    except Exception as exc:
        checks["db"] = f"error: {type(exc).__name__}"
        raise UnhealthyError(checks=checks) from exc

    return HealthOut(
        status="ok",
        checks=checks,
        config={
            "tau_retrieval": settings.tau_retrieval,
            "groq_model": settings.groq_model,
            "llm_provider": settings.llm_provider,
            "reranker_enabled": settings.reranker_enabled,
        },
    )
