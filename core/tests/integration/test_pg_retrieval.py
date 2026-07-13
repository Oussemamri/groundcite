"""Integration tests for the pg_vector / pg_lexical adapters (spec §7 steps 1a-1c).

These cover what fake ports cannot: the actual SQL. Assertions are written
against whichever corpus is ingested (see conftest) rather than hardcoded counts.
"""

from __future__ import annotations

import pytest

from groundcite.adapters.lexical.pg_lexical import make_pg_lexical_index
from groundcite.adapters.vector.pg_vector import make_pg_vector_index
from groundcite.config import get_settings

pytestmark = pytest.mark.integration


def _lex():  # type: ignore[no-untyped-def]
    return make_pg_lexical_index(get_settings().database_url)


def _vec():  # type: ignore[no-untyped-def]
    return make_pg_vector_index(get_settings().database_url)


def _a_clause_id(slug: str) -> str:
    """A clause_id that really exists in the ingested corpus."""
    import psycopg

    dsn = get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            """SELECT split_part(c.clause_path, '§', 2)
                 FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE d.slug = %s AND c.clause_path LIKE '%%§%%'
                LIMIT 1""",
            (slug,),
        ).fetchone()
    assert row is not None
    return str(row[0])


def test_lexical_search_ranks_and_respects_top_k(ingested_slug: str) -> None:
    hits = _lex().search("emergency exit marking", top_k=5, document_slugs=[ingested_slug])
    assert hits, "lexical search returned nothing for a corpus phrase"
    assert len(hits) <= 5
    scores = [s for _, s in hits]
    assert scores == sorted(scores, reverse=True), "must be ordered by ts_rank_cd desc"
    assert all(s > 0 for s in scores), "a @@ match must have a positive rank"


def test_lexical_search_empty_query_returns_nothing() -> None:
    assert _lex().search("   ", top_k=5) == []


def test_lexical_unknown_slug_filters_everything() -> None:
    assert _lex().search("emergency exit", top_k=5, document_slugs=["no-such-slug"]) == []


def test_match_clause_is_exact_not_prefix(ingested_slug: str) -> None:
    """The clause fast path must never prefix-match: '25.100' must not hit
    '25.1001'. This is why match_clause uses split_part equality, not LIKE."""
    lex = _lex()
    clause_id = _a_clause_id(ingested_slug)
    hits = lex.match_clause(clause_id, document_slugs=[ingested_slug])
    assert hits, f"exact clause id {clause_id!r} should fast-path"
    assert all(h.clause_path.endswith(f"§{clause_id}") for h in hits)

    # A strictly-longer id must not be reachable from the shorter one.
    longer = clause_id + "9"
    for h in lex.match_clause(longer, document_slugs=[ingested_slug]):
        assert h.clause_path.endswith(f"§{longer}")


def test_match_clause_accepts_full_clause_path(ingested_slug: str) -> None:
    lex = _lex()
    clause_id = _a_clause_id(ingested_slug)
    by_id = lex.match_clause(clause_id, document_slugs=[ingested_slug])
    full_path = by_id[0].clause_path
    by_path = lex.match_clause(full_path, document_slugs=[ingested_slug])
    assert {c.id for c in by_path} == {c.id for c in by_id}


def test_dense_self_retrieval_is_rank_one(ingested_slug: str) -> None:
    """Embedding a chunk's own content must retrieve that chunk at rank 1 with
    cosine ≈ 1.0 — the sanity check that the vector wire format, the HNSW index,
    and the score direction (1 - distance) all agree."""
    pytest.importorskip("FlagEmbedding")
    from groundcite.adapters.embedding.bge_m3_embed import make_bge_m3_embedder

    settings = get_settings()
    lex, vec = _lex(), _vec()
    probe = lex.match_clause(_a_clause_id(ingested_slug), document_slugs=[ingested_slug])[0]

    embedder = make_bge_m3_embedder(model_name=settings.embedding_model)
    query = embedder.embed([probe.content])[0]
    hits = vec.search(query, top_k=3, document_slugs=[ingested_slug])

    assert hits, "dense search returned nothing"
    top_chunk, top_score = hits[0]
    assert top_chunk.id == probe.id, "a chunk must be its own nearest neighbour"
    assert top_score == pytest.approx(1.0, abs=1e-3)
    assert [s for _, s in hits] == sorted((s for _, s in hits), reverse=True)


def test_dense_top_k_zero_short_circuits() -> None:
    assert _vec().search((0.0,) * 1024, top_k=0) == []
