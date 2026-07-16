"""Integration tests for the API read routes against the live compose Postgres
(CLAUDE rule 3; AD-7). Drives Starlette's ``TestClient`` against REAL services
built by the lifespan (build_services) — this is the one thing stubs cannot
cover: the route → service → repository → live-DB round trip. These auto-skip
when the DB is unreachable, so `pytest` in CI (api job: no DB) stays green.

A live GROUNDED ask (spends Groq tokens, needs the full model stack loaded)
is a MANUAL smoke — never in pytest. A live must-abstain ask costs nothing
(Gate A blocks before the LLM call, confirmed empirically: prompt_tokens=0)
and exercises the same real embed+rerank+DB+SSE wiring, so ONE such case is
worth having here.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def _dsn() -> str:
    from groundcite.config import get_settings

    return get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture(scope="module", autouse=True)
def _require_db() -> Iterator[None]:
    """Skip EVERY test in this module when compose Postgres is unreachable."""
    psycopg = pytest.importorskip("psycopg")
    try:
        with psycopg.connect(_dsn(), connect_timeout=3):
            pass
    except psycopg.Error as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"compose Postgres unreachable: {exc}")
    yield


@pytest.fixture(scope="module")
def live_client() -> Iterator[TestClient]:
    """Real app: lifespan builds real services (DB-backed repository). Uses the
    live ``get_settings()`` (core/.env). Models/embedder stay lazy — read routes
    touch only the repository, so no 2GB model load happens here."""
    app = create_app()
    # Enter the context manager so the lifespan runs build_services (AD-1).
    with TestClient(app) as c:
        yield c


def test_live_list_documents(live_client: TestClient) -> None:
    r = live_client.get("/api/v1/documents")
    assert r.status_code == 200
    docs = r.json()
    assert docs, "no documents in DB"
    assert any(d["slug"] == "far-25" for d in docs), "far-25 missing"
    assert all(d["license_note"] for d in docs), "license_note NOT NULL (§13)"


def test_live_get_document_far25_has_section_tree(live_client: TestClient) -> None:
    r = live_client.get("/api/v1/documents/far-25")
    assert r.status_code == 200
    body = r.json()
    assert body["document"]["slug"] == "far-25"
    assert body["sections"], "section tree empty for far-25"
    levels = [s["level"] for s in body["sections"]]
    assert levels == sorted(levels), "section tree ordered by (level, ordinal)"
    assert body["chunks"] is None  # default excludes chunks


def test_live_get_document_include_chunks(live_client: TestClient) -> None:
    r = live_client.get("/api/v1/documents/far-25?include=chunks")
    assert r.status_code == 200
    body = r.json()
    assert body["chunks"] is not None
    assert len(body["chunks"]) > 1000  # far-25 has 1,573 chunks


def test_live_get_chunk_by_id(live_client: TestClient) -> None:
    import psycopg

    with psycopg.connect(_dsn()) as conn:
        row = conn.execute("SELECT id FROM chunks LIMIT 1").fetchone()
    assert row is not None
    cid = str(row[0])
    r = live_client.get(f"/api/v1/chunks/{cid}")
    assert r.status_code == 200
    assert r.json()["id"] == cid


def test_live_healthz_ok(live_client: TestClient) -> None:
    r = live_client.get("/healthz")
    # DB is up; provider is not probed (deviation from AD-9, documented). 200.
    assert r.status_code == 200
    body = r.json()
    assert body["checks"]["db"] == "ok"
    assert body["config"]["tau_retrieval"] == 0.70


def test_live_unknown_slug_404_problem_json(live_client: TestClient) -> None:
    r = live_client.get("/api/v1/documents/no-such-slug")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


def test_live_eval_runs_list(live_client: TestClient) -> None:
    r = live_client.get("/api/v1/eval/runs")
    assert r.status_code == 200
    # May have 0+ runs depending on corpus state; contract is just no error.
    assert isinstance(r.json(), list)


def test_live_sse_ask_must_abstain_costs_no_tokens(live_client: TestClient) -> None:
    # Out-of-corpus question -> Gate A abstains on the reranker score alone,
    # before any LLM call (prompt_tokens/completion_tokens both 0) -- real
    # embed + rerank + Postgres + SSE wiring, zero Groq spend.
    r = live_client.post(
        "/api/v1/asks",
        json={
            "question": "What does DO-178C say about MC/DC coverage requirements?",
            "document_slugs": ["far-25"],
        },
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = [ln for ln in r.text.split("\r\n") if ln.startswith("event:")]
    assert events[0] == "event: stage"
    assert events[-1] == "event: final"
    assert '"status": "abstained"' in r.text
    assert '"usage": {"prompt_tokens": 0, "completion_tokens": 0}' in r.text
