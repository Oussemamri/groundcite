"""Unit tests for ``GET /documents`` + ``GET /documents/{slug}`` + ``GET /chunks/{id}``
(spec §9, §10; AD-4, AD-6). RFC-7807 shape asserted on 404s."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from groundcite.domain.entities import Chunk, Document, Section


def _doc(slug: str = "far-25") -> Document:
    return Document(
        id=uuid4(),
        slug=slug,
        standard_code="14 CFR Part 25",
        title="Airworthiness standards",
        organization="FAA",
        license_note="US public domain",
        ingested_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _section(doc_id: UUID) -> Section:
    return Section(
        id=uuid4(),
        document_id=doc_id,
        parent_id=None,
        clause_id="25.1309",
        title="Equipment",
        level=2,
        ordinal=10,
    )


def _chunk(doc_id: UUID, section_id: UUID) -> Chunk:
    return Chunk(
        id=uuid4(),
        document_id=doc_id,
        section_id=section_id,
        clause_path="14 CFR Part 25 §25.1309",
        content="[14 CFR Part 25 §25.1309] body",
        token_count=42,
    )


def test_list_documents_empty(client: TestClient) -> None:
    assert client.get("/api/v1/documents").json() == []


def test_list_documents_returns_models(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    stub_services.library.documents = [_doc()]
    c = make_client(stub_services)
    body = c.get("/api/v1/documents").json()
    assert body[0]["slug"] == "far-25"
    assert body[0]["standard_code"] == "14 CFR Part 25"
    assert body[0]["license_note"] == "US public domain"  # §13 always filled


def test_get_document_includes_section_tree(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    doc = _doc()
    sec = _section(doc.id)
    stub_services.library.by_slug = {"far-25": doc}
    stub_services.library.section_tree = [sec]
    body = make_client(stub_services).get("/api/v1/documents/far-25").json()
    assert body["document"]["slug"] == "far-25"
    assert [s["clause_id"] for s in body["sections"]] == ["25.1309"]
    assert body["chunks"] is None  # not included by default


def test_get_document_include_chunks(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    doc = _doc()
    sec = _section(doc.id)
    ch = _chunk(doc.id, sec.id)
    stub_services.library.by_slug = {"far-25": doc}
    stub_services.library.section_tree = [sec]
    stub_services.library.chunks = [ch]
    body = make_client(stub_services).get("/api/v1/documents/far-25?include=chunks").json()
    assert body["chunks"] is not None
    assert body["chunks"][0]["clause_path"] == "14 CFR Part 25 §25.1309"
    # Embedding is never serialized (1024 floats of no UI interest).
    assert "embedding" not in body["chunks"][0]


def test_get_document_unknown_slug_404_problem_json(client: TestClient) -> None:
    r = client.get("/api/v1/documents/no-such-slug")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["type"] == "https://groundcite.dev/problems/not-found"
    assert body["title"] == "Not Found"
    assert body["status"] == 404
    assert "document" in body["detail"] and "no-such-slug" in body["detail"]
    assert "instance" in body  # RFC-7807 stable-ish id


def test_get_chunk_ok(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    doc = _doc()
    sec = _section(doc.id)
    ch = _chunk(doc.id, sec.id)
    stub_services.library.chunk_by_id = {ch.id: ch}
    body = make_client(stub_services).get(f"/api/v1/chunks/{ch.id}").json()
    assert body["id"] == str(ch.id)
    assert body["token_count"] == 42


def test_get_chunk_unknown_id_404(client: TestClient) -> None:
    r = client.get(f"/api/v1/chunks/{uuid4()}")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["type"] == "https://groundcite.dev/problems/not-found"


def test_get_chunk_malformed_id_404_not_422(client: TestClient) -> None:
    r = client.get("/api/v1/chunks/not-a-uuid")
    assert r.status_code == 404  # a malformed id identifies no chunk
    assert r.json()["detail"] is not None
