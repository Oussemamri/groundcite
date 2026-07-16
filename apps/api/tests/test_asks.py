"""Unit tests for ``GET /asks/{id}`` replay (spec §9; AD-6 RFC-7807 on 404)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from groundcite.domain.entities import Ask
from groundcite.domain.results import AskStatus, Citation


def _ask(ask_id: UUID) -> Ask:
    return Ask(
        id=ask_id,
        question="What does §25.1309(b) require?",
        status=AskStatus.GROUNDED,
        answer_md="It must be extremely improbable.",
        confidence=0.91,
        latency_ms=4218,
        cost_usd=Decimal("0.00012"),
        pipeline_debug={"status": "grounded", "latency_ms": 4218},
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
    )


def _citations(ask_id: UUID, chunk_id: UUID) -> list[Citation]:
    return [Citation(chunk_id=chunk_id, rank=1, score=0.91, clause_path="14 CFR Part 25 §25.1309")]


def test_get_ask_replay_ok(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    aid = uuid4()
    cchunk = uuid4()
    ask = _ask(aid)
    cits = _citations(aid, cchunk)
    stub_services.ask.asks = {aid: ask}
    stub_services.ask.citations = {aid: cits}

    body = make_client(stub_services).get(f"/api/v1/asks/{aid}").json()
    assert body["id"] == str(aid)
    assert body["status"] == "grounded"
    assert body["answer_md"] == "It must be extremely improbable."
    assert body["confidence"] == 0.91
    assert body["citations"][0]["clause_path"] == "14 CFR Part 25 §25.1309"
    assert body["citations"][0]["rank"] == 1
    assert "pipeline_debug" in body
    assert body["question"] == "What does §25.1309(b) require?"


def test_get_ask_unknown_id_404(client: TestClient) -> None:
    r = client.get(f"/api/v1/asks/{uuid4()}")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["type"] == "https://groundcite.dev/problems/not-found"


def test_get_ask_malformed_id_404(client: TestClient) -> None:
    r = client.get("/api/v1/asks/not-a-uuid")
    assert r.status_code == 404


def test_get_ask_abstention_has_empty_citations(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    aid = uuid4()
    ask = _ask(aid).model_copy(
        update={"status": AskStatus.ABSTAINED, "answer_md": None, "confidence": 0.21}
    )
    stub_services.ask.asks = {aid: ask}
    stub_services.ask.citations = {aid: []}  # abstentions have no citations
    body = make_client(stub_services).get(f"/api/v1/asks/{aid}").json()
    assert body["status"] == "abstained"
    assert body["citations"] == []
    assert body["answer_md"] is None
