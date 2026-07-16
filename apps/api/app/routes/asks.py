"""Read route: ask replay (spec §9 ``GET /asks/{id}``).

Returns the answer + citations + ``pipeline_debug`` (spec §9: "answer +
citations + debug"). The streamed POST happens in Phase 3 (``asks_stream.py``);
this is the replay of a past Ask. 404 for unknown id → RFC-7807 (AD-6).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.deps import get_services
from app.errors import NotFoundError, not_found_or_raise
from app.models import AskOut
from groundcite.container import Services

router = APIRouter(prefix="/api/v1", tags=["asks"])


@router.get("/asks/{ask_id}", response_model=AskOut)
def get_ask(ask_id: str, services: Services = Depends(get_services)) -> AskOut:
    try:
        cid = UUID(ask_id)
    except ValueError as exc:
        raise NotFoundError(slug=ask_id, label="ask") from exc
    ask = not_found_or_raise(services.ask.get_ask(cid), slug=ask_id, label="ask")
    citations = services.ask.get_ask_citations(cid)
    return AskOut.from_domain(ask, citations)
