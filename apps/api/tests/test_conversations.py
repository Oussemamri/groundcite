"""Unit tests for ``GET /conversations`` / ``GET /conversations/{id}``
(spec §9, Week 6)."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from groundcite.domain.entities import Ask
from groundcite.domain.results import AskStatus


def _conversation(cid: UUID, **overrides: object) -> object:
    base: dict[str, object] = {
        "id": cid,
        "title": "What does §25.1309(b) require?",
        "created_at": None,
        "turn_count": 1,
        "latest_status": AskStatus.GROUNDED,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _ask(ask_id: UUID, **overrides: object) -> Ask:
    base: dict[str, object] = {
        "id": ask_id,
        "question": "What does §25.1309(b) require?",
        "status": AskStatus.GROUNDED,
        "answer_md": "It must be extremely improbable.",
        "confidence": 0.91,
    }
    base.update(overrides)
    return Ask(**base)  # type: ignore[arg-type]


def test_list_conversations_empty(client: TestClient) -> None:
    assert client.get("/api/v1/conversations").json() == []


def test_list_conversations_ok(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    cid = uuid4()
    stub_services.ask.conversations = {cid: _conversation(cid)}

    body = make_client(stub_services).get("/api/v1/conversations").json()

    assert len(body) == 1
    assert body[0]["id"] == str(cid)
    assert body[0]["title"] == "What does §25.1309(b) require?"
    assert body[0]["turn_count"] == 1
    assert body[0]["latest_status"] == "grounded"


def test_get_conversation_unknown_id_404(client: TestClient) -> None:
    r = client.get(f"/api/v1/conversations/{uuid4()}")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


def test_get_conversation_malformed_id_404(client: TestClient) -> None:
    r = client.get("/api/v1/conversations/not-a-uuid")
    assert r.status_code == 404


def test_get_conversation_detail_returns_full_turn_history(  # type: ignore[no-untyped-def]
    make_client, stub_services
) -> None:
    cid = uuid4()
    aid1, aid2 = uuid4(), uuid4()
    stub_services.ask.conversations = {cid: _conversation(cid, turn_count=2)}
    stub_services.ask.conversation_asks = {
        cid: [
            _ask(aid1, question="first turn"),
            _ask(aid2, question="second turn", status=AskStatus.ABSTAINED, answer_md=None),
        ]
    }
    stub_services.ask.citations = {aid1: [], aid2: []}

    body = make_client(stub_services).get(f"/api/v1/conversations/{cid}").json()

    assert body["conversation"]["id"] == str(cid)
    assert len(body["asks"]) == 2
    assert body["asks"][0]["question"] == "first turn"
    assert body["asks"][1]["status"] == "abstained"
