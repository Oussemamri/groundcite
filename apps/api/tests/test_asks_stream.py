"""Unit tests for ``POST /api/v1/asks`` (spec §7, §9; AD-2).

Scripted event streams through ``StubAsk.events_factory`` -- no network, no
DB, no model load (CLAUDE rule 3). Parses the raw SSE wire frames (sse-
starlette uses ``\\r\\n`` line endings) to assert event NAMES and ORDER,
mirroring the terminal-event-uniqueness contract already unit-tested at the
service layer in core (``test_ask_generation.py``) -- this layer only needs
to prove the route doesn't distort that contract in transit.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi.testclient import TestClient

from groundcite.domain.results import AskEvent, AskEventType


def _parse_sse(text: str) -> list[tuple[str, str]]:
    """[(event_name, data_json_str), ...] from a raw SSE response body."""
    frames = [f for f in text.split("\r\n\r\n") if f.strip()]
    out: list[tuple[str, str]] = []
    for frame in frames:
        event_name = ""
        data = ""
        for line in frame.split("\r\n"):
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = line[len("data:") :].strip()
        out.append((event_name, data))
    return out


def _grounded_events() -> Iterator[AskEvent]:
    yield AskEvent(type=AskEventType.STAGE, data={"stage": "retrieving"})
    yield AskEvent(type=AskEventType.STAGE, data={"stage": "reranking"})
    yield AskEvent(type=AskEventType.STAGE, data={"stage": "generating"})
    yield AskEvent(type=AskEventType.TOKEN, data={"text": "Hello"})
    yield AskEvent(type=AskEventType.TOKEN, data={"text": " world"})
    yield AskEvent(type=AskEventType.CITATIONS, data={"citations": [{"chunk_id": "c1"}]})
    yield AskEvent(
        type=AskEventType.FINAL,
        data={"ask_id": "a1", "status": "grounded", "answer": {"answer_md": "Hello world"}},
    )


def _abstained_events() -> Iterator[AskEvent]:
    yield AskEvent(type=AskEventType.STAGE, data={"stage": "retrieving"})
    yield AskEvent(type=AskEventType.STAGE, data={"stage": "reranking"})
    yield AskEvent(
        type=AskEventType.FINAL,
        data={"status": "abstained", "abstention": {"reason": "weak_retrieval"}},
    )


def _error_events() -> Iterator[AskEvent]:
    yield AskEvent(type=AskEventType.STAGE, data={"stage": "retrieving"})
    yield AskEvent(type=AskEventType.ERROR, data={"message": "simulated failure"})


def test_grounded_stream_event_order(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    stub_services.ask.events_factory = _grounded_events
    r = make_client(stub_services).post("/api/v1/asks", json={"question": "q?"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    frames = _parse_sse(r.text)
    names = [n for n, _ in frames]
    assert names == ["stage", "stage", "stage", "token", "token", "citations", "final"]
    # Exactly one terminal event (spec §7 contract), and it is last.
    terminals = [n for n in names if n in ("final", "error")]
    assert len(terminals) == 1
    assert names[-1] == "final"


def test_abstained_stream_skips_generation_stage(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    stub_services.ask.events_factory = _abstained_events
    r = make_client(stub_services).post("/api/v1/asks", json={"question": "q?"})
    names = [n for n, _ in _parse_sse(r.text)]
    assert "token" not in names
    assert "citations" not in names
    assert names[-1] == "final"
    assert '"reason": "weak_retrieval"' in r.text


def test_error_stream_terminates_with_error_event(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    stub_services.ask.events_factory = _error_events
    r = make_client(stub_services).post("/api/v1/asks", json={"question": "q?"})
    names = [n for n, _ in _parse_sse(r.text)]
    assert names == ["stage", "error"]
    assert '"message": "simulated failure"' in r.text


def test_request_body_rejects_unknown_fields(client: TestClient) -> None:
    r = client.post("/api/v1/asks", json={"question": "q?", "bogus_field": 1})
    assert r.status_code == 422


def test_request_body_requires_question(client: TestClient) -> None:
    r = client.post("/api/v1/asks", json={})
    assert r.status_code == 422


def test_document_slugs_are_passed_through(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    seen: dict[str, object] = {}

    def _capturing_ask(
        question: str,
        document_slugs: list[str] | None = None,
        conversation_id: object | None = None,
    ) -> Iterator[AskEvent]:
        seen["question"] = question
        seen["document_slugs"] = document_slugs
        yield AskEvent(type=AskEventType.FINAL, data={"status": "abstained"})

    stub_services.ask.ask = _capturing_ask
    make_client(stub_services).post(
        "/api/v1/asks", json={"question": "q?", "document_slugs": ["far-25"]}
    )
    assert seen == {"question": "q?", "document_slugs": ["far-25"]}


# --- Week 6: conversation_id --------------------------------------------------


def test_conversation_id_auto_created_when_absent(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    seen: dict[str, object] = {}

    def _capturing_ask(
        question: str,
        document_slugs: list[str] | None = None,
        conversation_id: object | None = None,
    ) -> Iterator[AskEvent]:
        seen["conversation_id"] = conversation_id
        yield AskEvent(type=AskEventType.FINAL, data={"status": "abstained"})

    stub_services.ask.ask = _capturing_ask
    r = make_client(stub_services).post("/api/v1/asks", json={"question": "a fresh question"})
    assert r.status_code == 200
    assert seen["conversation_id"] is not None
    # The auto-created conversation is now discoverable via list_conversations.
    [conv] = stub_services.ask.conversations.values()
    assert conv.title == "a fresh question"
    assert seen["conversation_id"] == conv.id


def test_conversation_id_truncates_long_titles(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    stub_services.ask.events_factory = _abstained_events
    long_question = "x" * 200
    make_client(stub_services).post("/api/v1/asks", json={"question": long_question})
    [conv] = stub_services.ask.conversations.values()
    assert len(conv.title) == 80
    assert conv.title.endswith("…")


def test_conversation_id_passed_through_when_provided(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    from uuid import UUID, uuid4

    seen: dict[str, object] = {}
    existing_id = uuid4()

    def _capturing_ask(
        question: str,
        document_slugs: list[str] | None = None,
        conversation_id: object | None = None,
    ) -> Iterator[AskEvent]:
        seen["conversation_id"] = conversation_id
        yield AskEvent(type=AskEventType.FINAL, data={"status": "abstained"})

    stub_services.ask.ask = _capturing_ask
    r = make_client(stub_services).post(
        "/api/v1/asks", json={"question": "q?", "conversation_id": str(existing_id)}
    )
    assert r.status_code == 200
    assert seen["conversation_id"] == existing_id
    assert isinstance(seen["conversation_id"], UUID)
    # No new conversation was auto-created -- the given id was used as-is.
    assert stub_services.ask.conversations == {}


def test_malformed_conversation_id_404(client: TestClient) -> None:
    r = client.post("/api/v1/asks", json={"question": "q?", "conversation_id": "not-a-uuid"})
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
