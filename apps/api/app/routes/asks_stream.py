"""Write route: the streamed ask (spec §7, §9 ``POST /asks``; AD-2).

``AskService.ask()`` is a SYNC, blocking generator (reranker CPU + LLM
network) yielding ``AskEvent``s: STAGE(retrieving) -> STAGE(reranking) ->
[Gate A abstain -> FINAL] or [STAGE(generating) -> TOKEN* -> CITATIONS ->
FINAL] | ERROR. Exactly one terminal event (spec §7 contract, already
enforced by ``ask()`` itself -- this route does not re-check it).

``sse-starlette``'s ``EventSourceResponse`` accepts a plain sync ``Iterator``
directly and iterates it in Starlette's threadpool, so the blocking
generator never blocks the event loop (AD-2) -- no ``async for`` / no
manual thread offload needed here. Event names and payloads are the core
``AskEvent`` untouched; this route does not invent a second event
vocabulary (spec §7: API and web share one enum) -- ``apps/web/lib/sse.ts``
mirrors ``AskEventType`` exactly.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.deps import get_services
from app.logging_conf import get_logger
from groundcite.container import Services
from groundcite.domain.results import AskEvent, AskEventType

router = APIRouter(prefix="/api/v1", tags=["asks"])


class AskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    document_slugs: list[str] | None = None


def _to_sse(event: AskEvent) -> ServerSentEvent:
    return ServerSentEvent(event=event.type.value, data=json.dumps(event.data))


def _stream(services: Services, body: AskIn) -> Iterator[ServerSentEvent]:
    log = get_logger("app.asks_stream")
    log.info("ask_started", question_len=len(body.question), slugs=body.document_slugs)
    for event in services.ask.ask(body.question, document_slugs=body.document_slugs):
        if event.type is AskEventType.STAGE:
            log.info("ask_stage", stage=event.data.get("stage"))
        elif event.type in (AskEventType.FINAL, AskEventType.ERROR):
            log.info(
                "ask_terminal",
                event_type=event.type.value,
                ask_id=event.data.get("ask_id"),
                status=event.data.get("status"),
            )
        yield _to_sse(event)


@router.post("/asks")
def ask(body: AskIn, services: Services = Depends(get_services)) -> EventSourceResponse:
    return EventSourceResponse(_stream(services, body))
