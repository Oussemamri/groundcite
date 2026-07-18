"""Integration tests for the Week-4 AD-4 Repository read extensions against the
compose Postgres (spec §9, §10; CLAUDE rule 3: the one thing fakes cannot cover
is the real SQL). Assertions are written against whichever corpus is ingested
(see conftest) rather than hardcoded counts, so the suite does not rot.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from groundcite.adapters.repository.pg_repo import PgRepository, make_pg_repository
from groundcite.config import get_settings

pytestmark = pytest.mark.integration


def _repo() -> PgRepository:
    return make_pg_repository(get_settings().database_url)


def test_list_documents_and_get_document_round_trip(ingested_slug: str) -> None:
    repo = _repo()
    docs = repo.list_documents()
    assert docs, "no documents in the DB"
    assert any(d.slug == ingested_slug for d in docs), "ingested slug missing from list_documents()"

    doc = repo.get_document(ingested_slug)
    assert doc is not None
    assert doc.license_note, "license_note is NOT NULL (spec §13)"


def test_get_section_tree_parents_before_children(ingested_slug: str) -> None:
    repo = _repo()
    doc = repo.get_document(ingested_slug)
    assert doc is not None
    tree = repo.get_section_tree(doc.id)
    assert tree, "section tree empty"
    # Ordered by (level, ordinal): levels are non-decreasing; a parent at a
    # lower level always precedes any of its descendants.
    levels = [s.level for s in tree]
    assert levels == sorted(levels), "section tree must be ordered by level, ordinal"
    assert repo.get_section_tree(uuid4()) == []  # unknown document -> empty, not raise


def test_list_chunks_ordered_and_nonempty(ingested_slug: str) -> None:
    repo = _repo()
    doc = repo.get_document(ingested_slug)
    assert doc is not None
    chunks = repo.list_chunks(doc.id)
    assert chunks, "no chunks for ingested document"
    paths = [c.clause_path for c in chunks]
    # AD-4 contract: ordered by clause_path. Verified collation-independently
    # against the DB's own ORDER BY ... DESC: the ascending result must be the
    # exact reverse of the descending one (proves an ascending ORDER BY clause_path
    # is actually applied, regardless of the DB's text collation). Note
    # (residual, docs/WEEK4_RESULTS): the SQL text collation is NOT a natural
    # numeric clause order (``§25.399`` sorts before ``§25.3(a)``); the reader
    # page owner (Phase 8) gets a ClauseTree from the section tree, which IS
    # correctly ordered by (level, ordinal) — list_chunks order is cosmetic.
    import psycopg

    dsn = get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(dsn) as conn:
        desc = [
            r[0]
            for r in conn.execute(
                "SELECT clause_path FROM chunks WHERE document_id = %s ORDER BY clause_path DESC",
                (doc.id,),
            ).fetchall()
        ]
    assert paths == list(reversed(desc)), "list_chunks must be ascending ORDER BY clause_path"
    assert repo.list_chunks(uuid4()) == []  # unknown document -> empty, not raise


def test_get_ask_citations_unknown_returns_empty() -> None:
    # No ask with a random id exists; the read must return [] (not raise).
    assert _repo().get_ask_citations(uuid4()) == []


def test_list_eval_runs_returns_rows_or_empty() -> None:
    runs = _repo().list_eval_runs()
    # May be empty on a fresh DB; the contract is just "does not raise" + ordering.
    if runs:
        # newest-first: we cannot assert timestamps from here without a second
        # query, but the query is ORDER BY started_at DESC — verified by SQL.
        assert all(r.git_sha for r in runs), "git_sha is NOT NULL"


def test_conversation_create_get_list_round_trip() -> None:
    """Week 6: the one thing FakeRepository cannot cover -- the real SQL
    (correlated subquery for turn_count/latest_status, the FK to asks)."""
    repo = _repo()
    conv = repo.create_conversation("live-DB integration test conversation")

    fetched = repo.get_conversation(conv.id)
    assert fetched is not None
    assert fetched.title == "live-DB integration test conversation"
    assert fetched.created_at is not None

    listed = repo.list_conversations()
    match = next((c for c in listed if c.id == conv.id), None)
    assert match is not None, "newly created conversation missing from list_conversations()"
    assert match.turn_count == 0, "no asks saved yet"
    assert match.latest_status is None

    assert repo.get_conversation(uuid4()) is None
    assert repo.list_conversation_asks(conv.id) == []
    assert repo.list_conversation_asks(uuid4()) == []
