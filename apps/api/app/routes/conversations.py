"""Conversation read routes (spec §9, Week 6).

- ``GET /api/v1/conversations`` — list, newest first.
- ``GET /api/v1/conversations/{id}`` — one conversation's full turn history.

Conversations group already-independent Asks for the `/ask` chat UI; they
carry NO generation state of their own (spec §3.2 "one ask = one pipeline
run" is unchanged). Routes are thin (parse -> service -> serialize); 404 for
an unknown id via the existing ``NotFoundError`` -> RFC-7807 (AD-6).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_services
from app.errors import coerce_id, not_found_or_raise
from app.models import AskOut, ConversationDetailOut, ConversationOut
from groundcite.container import Services

router = APIRouter(prefix="/api/v1", tags=["conversations"])


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(services: Services = Depends(get_services)) -> list[ConversationOut]:
    return [ConversationOut.from_domain(c) for c in services.ask.list_conversations()]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(
    conversation_id: str, services: Services = Depends(get_services)
) -> ConversationDetailOut:
    cid = coerce_id(conversation_id, label="conversation")
    conversation = not_found_or_raise(
        services.ask.get_conversation(cid), slug=conversation_id, label="conversation"
    )
    asks = services.ask.list_conversation_asks(cid)
    # get_conversation() itself never populates turn_count/latest_status --
    # that's list_conversations()'s SQL-derived job (see Conversation's
    # docstring). Here the route already has the full turn list in hand, so
    # it derives them from that instead of a second, redundant DB read
    # (same "compute in the route from already-fetched data" pattern as
    # Week 5's EvalRunAggregatesOut). list_conversation_asks orders ascending
    # by created_at, so the last element is the latest turn.
    summary = ConversationOut.from_domain(conversation)
    summary = summary.model_copy(
        update={
            "turn_count": len(asks),
            "latest_status": asks[-1].status.value if asks else None,
        }
    )
    return ConversationDetailOut(
        conversation=summary,
        asks=[AskOut.from_domain(ask, services.ask.get_ask_citations(ask.id)) for ask in asks],
    )
