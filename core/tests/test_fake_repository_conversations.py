"""Unit tests for FakeRepository's Week 6 conversation methods directly
(rule 3) -- the Repository-port-level behavior AskService's thin delegates
sit on top of (covered end-to-end in
``tests/services/test_ask_conversations.py``)."""

from __future__ import annotations

from uuid import UUID, uuid4

from groundcite.domain.entities import Ask
from groundcite.domain.results import AskStatus
from tests.fakes import FakeRepository


def _ask(conversation_id: UUID, status: AskStatus = AskStatus.GROUNDED) -> Ask:
    return Ask(id=uuid4(), question="q?", status=status, conversation_id=conversation_id)


def test_create_conversation_is_retrievable_by_id() -> None:
    repo = FakeRepository()
    conv = repo.create_conversation("What does §25.1309(b) require?")
    assert repo.get_conversation(conv.id) == conv


def test_get_conversation_unknown_id_returns_none() -> None:
    repo = FakeRepository()
    assert repo.get_conversation(uuid4()) is None


def test_list_conversations_empty() -> None:
    repo = FakeRepository()
    assert repo.list_conversations() == []


def test_list_conversations_newest_first_with_turn_count_and_latest_status() -> None:
    repo = FakeRepository()
    older = repo.create_conversation("older")
    newer = repo.create_conversation("newer")
    # FakeRepository stamps created_at at creation time -- newer really is newer.
    repo.asks[uuid4()] = _ask(older.id, AskStatus.GROUNDED)
    a1 = _ask(older.id, AskStatus.ABSTAINED)
    repo.asks[a1.id] = a1

    listed = repo.list_conversations()

    assert [c.id for c in listed] == [newer.id, older.id]
    older_listed = next(c for c in listed if c.id == older.id)
    assert older_listed.turn_count == 2
    newer_listed = next(c for c in listed if c.id == newer.id)
    assert newer_listed.turn_count == 0
    assert newer_listed.latest_status is None


def test_list_conversation_asks_ordered_and_scoped_to_one_conversation() -> None:
    repo = FakeRepository()
    conv_a = repo.create_conversation("a")
    conv_b = repo.create_conversation("b")
    a1 = _ask(conv_a.id)
    a2 = _ask(conv_a.id)
    b1 = _ask(conv_b.id)
    for a in (a1, a2, b1):
        repo.asks[a.id] = a

    asks_a = repo.list_conversation_asks(conv_a.id)

    assert {a.id for a in asks_a} == {a1.id, a2.id}
    assert repo.list_conversation_asks(uuid4()) == []
