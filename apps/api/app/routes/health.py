"""Health route (spec §9 GET /healthz).

P5: returns a static OK so the container/orchestration has a liveness signal.
Week 4 extends this to check DB + one cheap provider call (spec §9, §12).
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe. Extended to DB + provider reachability in Week 4."""
    return {"status": "ok"}
