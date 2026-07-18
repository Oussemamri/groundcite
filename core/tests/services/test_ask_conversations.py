"""Unit tests for Week 6's conversation grouping (spec §5, §7 conversation_id
tag). Fake ports only (rule 3).

Covers exactly what Week 6 AD-1 promises and nothing more: conversation_id
is a TAG on the persisted Ask row and the terminal event's data -- it never
changes retrieval or generation (spec §3.2, "one ask = one pipeline run" is
unchanged). AskService's create/get/list conversation methods are thin
Repository delegates, same shape as get_ask/get_ask_citations.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from groundcite.domain.entities import Chunk
from groundcite.domain.results import AskEventType, AskStatus, TokenUsage
from groundcite.services.ask import AskService
from tests.fakes import (
    FakeEmbedder,
    FakeLexicalIndex,
    FakeLLM,
    FakeRepository,
    FakeReranker,
    FakeVectorIndex,
)


def _chunk(clause: str) -> Chunk:
    return Chunk(
        id=uuid4(),
        document_id=UUID(int=1),
        section_id=UUID(int=2),
        clause_path=f"14 CFR Part 25 §{clause}",
        content=f"body of {clause}",
        token_count=10,
    )


def _valid_json(chunk: Chunk, answer: str = "The answer.") -> str:
    return (
        f'{{"answer_md": "{answer}", "citations": '
        f'[{{"chunk_id": "{chunk.id}", "claim": "grounding claim"}}], "insufficient": false}}'
    )


def _grounded_service(
    repository: FakeRepository | None,
) -> tuple[AskService, Chunk]:
    c = _chunk("25.1309")
    svc = AskService(
        embedder=FakeEmbedder(),
        vector_index=FakeVectorIndex([(c, 0.9)]),
        lexical_index=FakeLexicalIndex([]),
        reranker=FakeReranker({c.clause_path: 0.9}),
        llm=FakeLLM(_valid_json(c), TokenUsage(prompt_tokens=10, completion_tokens=5)),
        tau_retrieval=0.35,
        repository=repository,
    )
    return svc, c


def _abstaining_service(repository: FakeRepository | None) -> AskService:
    c = _chunk("25.999")
    return AskService(
        embedder=FakeEmbedder(),
        vector_index=FakeVectorIndex([(c, 0.9)]),
        lexical_index=FakeLexicalIndex([]),
        reranker=FakeReranker({c.clause_path: 0.10}),  # below tau -> Gate A abstains
        llm=FakeLLM("never reached", TokenUsage(prompt_tokens=0, completion_tokens=0)),
        tau_retrieval=0.35,
        repository=repository,
    )


# --- conversation_id tags the grounded path, doesn't change it ---------------


def test_grounded_ask_with_conversation_id_tags_the_persisted_row() -> None:
    repo = FakeRepository()
    svc, _ = _grounded_service(repo)
    conv = repo.create_conversation("What does §25.1309(b) require?")

    events = list(svc.ask("What does §25.1309(b) require?", conversation_id=conv.id))

    final = next(e for e in events if e.type is AskEventType.FINAL)
    assert final.data["conversation_id"] == str(conv.id)
    assert final.data["status"] == "grounded"
    [saved_ask] = repo.asks.values()
    assert saved_ask.conversation_id == conv.id


def test_grounded_ask_without_conversation_id_leaves_it_none() -> None:
    """Today's callers (CLI, EvalService) never pass conversation_id -- must
    keep working completely unchanged."""
    repo = FakeRepository()
    svc, _ = _grounded_service(repo)

    events = list(svc.ask("What does §25.1309(b) require?"))

    final = next(e for e in events if e.type is AskEventType.FINAL)
    assert final.data["conversation_id"] is None
    [saved_ask] = repo.asks.values()
    assert saved_ask.conversation_id is None


# --- conversation_id tags the abstained path too ------------------------------


def test_abstained_ask_with_conversation_id_tags_the_persisted_row() -> None:
    repo = FakeRepository()
    svc = _abstaining_service(repo)
    conv = repo.create_conversation("An out-of-corpus question")

    events = list(svc.ask("An out-of-corpus question", conversation_id=conv.id))

    final = next(e for e in events if e.type is AskEventType.FINAL)
    assert final.data["status"] == "abstained"
    assert final.data["conversation_id"] == str(conv.id)
    [saved_ask] = repo.asks.values()
    assert saved_ask.conversation_id == conv.id
    assert saved_ask.status is AskStatus.ABSTAINED


# --- conversation_id tags the ERROR path too (conversation already exists) ---


def test_error_event_carries_conversation_id() -> None:
    class _ExplodingLLM:
        model_name = "boom"

        def stream(self, system: str, user: str):  # type: ignore[no-untyped-def]
            raise ValueError("simulated provider failure")
            yield  # pragma: no cover - makes this a generator function

    c = _chunk("25.1")
    repo = FakeRepository()
    conv = repo.create_conversation("q?")
    svc = AskService(
        embedder=FakeEmbedder(),
        vector_index=FakeVectorIndex([(c, 0.9)]),
        lexical_index=FakeLexicalIndex([]),
        reranker=FakeReranker({c.clause_path: 0.9}),
        llm=_ExplodingLLM(),
        tau_retrieval=0.35,
        repository=repo,
    )

    events = list(svc.ask("q?", conversation_id=conv.id))

    assert events[-1].type is AskEventType.ERROR
    assert events[-1].data["conversation_id"] == str(conv.id)
    # A real, accepted edge case (Week 6 plan): the conversation row exists,
    # but no Ask row is ever persisted on this path (mirrors the pre-Week-6
    # behavior -- only the FINAL-reaching branches call save_ask).
    assert repo.asks == {}


# --- AskService conversation methods are thin Repository delegates -----------


def test_create_get_list_conversations_delegate_to_repository() -> None:
    repo = FakeRepository()
    svc, _ = _grounded_service(repo)

    created = svc.create_conversation("My first question")
    assert created is not None
    assert svc.get_conversation(created.id) == created

    list(svc.ask("My first question", conversation_id=created.id))
    [listed] = svc.list_conversations()
    assert listed.id == created.id
    assert listed.turn_count == 1
    assert listed.latest_status is AskStatus.GROUNDED

    [ask] = svc.list_conversation_asks(created.id)
    assert ask.conversation_id == created.id


def test_conversation_methods_return_empty_without_a_repository() -> None:
    svc, _ = _grounded_service(None)
    assert svc.create_conversation("x") is None
    assert svc.get_conversation(uuid4()) is None
    assert svc.list_conversations() == []
    assert svc.list_conversation_asks(uuid4()) == []
