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
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.deps import get_services
from app.errors import coerce_id
from app.logging_conf import get_logger
from groundcite.container import Services
from groundcite.domain.results import AskEvent, AskEventType

router = APIRouter(prefix="/api/v1", tags=["asks"])


_TITLE_MAX = 80


class AskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    document_slugs: list[str] | None = None
    # Week 6: groups this ask under a Conversation for the /ask chat UI.
    # Omitted -> the route auto-creates a new conversation (title = the
    # opening question, truncated). This ONLY tags the persisted Ask row and
    # the terminal event's data -- no prior-turn context is ever read or
    # passed to the LLM (spec §3.2 unchanged).
    conversation_id: str | None = None


def _to_sse(event: AskEvent) -> ServerSentEvent:
    return ServerSentEvent(event=event.type.value, data=json.dumps(event.data))


def _title_from_question(question: str) -> str:
    q = question.strip()
    return q if len(q) <= _TITLE_MAX else q[: _TITLE_MAX - 1].rstrip() + "…"


def _stream(
    services: Services, body: AskIn, conversation_id: UUID | None
) -> Iterator[ServerSentEvent]:
    log = get_logger("app.asks_stream")
    log.info(
        "ask_started",
        question_len=len(body.question),
        slugs=body.document_slugs,
        conversation_id=str(conversation_id) if conversation_id else None,
    )
    for event in services.ask.ask(
        body.question, document_slugs=body.document_slugs, conversation_id=conversation_id
    ):
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
    conversation_id: UUID | None
    if body.conversation_id is not None:
        conversation_id = coerce_id(body.conversation_id, label="conversation")
    else:
        conversation = services.ask.create_conversation(_title_from_question(body.question))
        conversation_id = conversation.id if conversation is not None else None
    return EventSourceResponse(_stream(services, body, conversation_id))
