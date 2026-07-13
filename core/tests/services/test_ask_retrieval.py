"""Unit tests for AskService.retrieve (spec §7 steps 0-3, §17 rule 3).

Fake ports only — no DB, no network, no model. These pin the ORCHESTRATION:
which stage feeds which, the rank-1 clause guarantee, the slug filter, and the
reranker on/off paths. The ranking math itself is pinned in test_fusion.py.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from groundcite.domain.entities import Chunk
from groundcite.services.ask import AskService
from groundcite.services.fusion import CLAUSE_FAST_PATH_SCORE
from tests.fakes import FakeEmbedder, FakeLexicalIndex, FakeReranker, FakeVectorIndex


def _chunk(clause: str) -> Chunk:
    return Chunk(
        id=uuid4(),
        document_id=UUID(int=1),
        section_id=UUID(int=2),
        clause_path=f"14 CFR Part 25 §{clause}",
        content=f"body of {clause}",
        token_count=10,
    )


def _service(
    dense: list[tuple[Chunk, float]] | None = None,
    lexical: list[tuple[Chunk, float]] | None = None,
    clause_hits: dict[str, list[Chunk]] | None = None,
    reranker: FakeReranker | None = None,
    **kwargs: int,
) -> tuple[AskService, FakeVectorIndex, FakeLexicalIndex]:
    vec = FakeVectorIndex(dense or [])
    lex = FakeLexicalIndex(lexical or [], clause_hits or {})
    svc = AskService(
        embedder=FakeEmbedder(),
        vector_index=vec,
        lexical_index=lex,
        reranker=reranker,
        **kwargs,
    )
    return svc, vec, lex


def test_fuses_dense_and_lexical_into_ranked_context() -> None:
    both, dense_only = _chunk("25.both"), _chunk("25.dense")
    svc, _, _ = _service(
        dense=[(dense_only, 0.99), (both, 0.10)],
        lexical=[(both, 9.9)],
    )

    result = svc.retrieve("how are exits marked?")

    assert [c.clause_path for c in result.chunks] == [
        "14 CFR Part 25 §25.both",
        "14 CFR Part 25 §25.dense",
    ]
    assert result.reranked is False
    assert result.clause_ids == ()


def test_clause_question_fires_the_fast_path_at_rank_one() -> None:
    """A question naming §25.1309(b) must put that clause first, ahead of
    whatever dense/lexical liked (spec §7 step 1c)."""
    exact = _chunk("25.1309(b)")
    fuzzy = _chunk("25.999")
    svc, _, lex = _service(
        dense=[(fuzzy, 0.99)],
        lexical=[(fuzzy, 9.9)],
        clause_hits={"25.1309(b)": [exact]},
    )

    result = svc.retrieve("What does §25.1309(b) require?")

    assert result.clause_ids == ("25.1309(b)",)
    assert lex.matched == ["25.1309(b)"], "the detected clause id is looked up exactly"
    assert result.chunks[0].clause_path == "14 CFR Part 25 §25.1309(b)"
    assert result.chunks[0].score == CLAUSE_FAST_PATH_SCORE


def test_semantic_question_does_not_call_the_fast_path() -> None:
    svc, _, lex = _service(dense=[(_chunk("25.1"), 0.5)])
    result = svc.retrieve("What failure probability is acceptable?")
    assert result.clause_ids == ()
    assert lex.matched == [], "no clause id ⇒ no exact-match lookup"


def test_document_slugs_filter_reaches_both_indexes() -> None:
    svc, vec, _ = _service(dense=[(_chunk("25.1"), 0.5)])
    svc.retrieve("exits", document_slugs=["far-25"])
    assert vec.calls[0][1] == ("far-25",)


def test_candidate_widths_come_from_config() -> None:
    """candidates_dense / candidates_lexical are injected (spec §7 defaults 30/30)."""
    svc, vec, _ = _service(candidates_dense=7, candidates_lexical=9)
    svc.retrieve("anything")
    assert vec.calls[0][0] == 7


def test_reranker_reorders_and_truncates_to_context_k() -> None:
    a, b, c = _chunk("25.a"), _chunk("25.b"), _chunk("25.c")
    reranker = FakeReranker(
        scores={
            "14 CFR Part 25 §25.c": 0.9,  # cross-encoder disagrees with fusion
            "14 CFR Part 25 §25.a": 0.5,
            "14 CFR Part 25 §25.b": 0.1,
        }
    )
    svc, _, _ = _service(
        dense=[(a, 0.9), (b, 0.8), (c, 0.1)],
        lexical=[(a, 9.0)],
        reranker=reranker,
        context_k=2,
    )

    result = svc.retrieve("q")

    assert result.reranked is True
    assert [c.clause_path for c in result.chunks] == [
        "14 CFR Part 25 §25.c",
        "14 CFR Part 25 §25.a",
    ]
    assert result.chunks[0].score == 0.9
    assert reranker.calls == [("q", 2)]
    # The wider fused list is still carried for abstention top_passages (§7).
    assert len(result.candidates) == 3


def test_reranker_off_keeps_fusion_order() -> None:
    a, b = _chunk("25.a"), _chunk("25.b")
    svc, _, _ = _service(dense=[(a, 0.9), (b, 0.8)], reranker=None, context_k=1)
    result = svc.retrieve("q")
    assert result.reranked is False
    assert [c.clause_path for c in result.chunks] == ["14 CFR Part 25 §25.a"]


def test_top_k_override_wins_over_context_k() -> None:
    chunks = [(_chunk(f"25.{i}"), 1.0 - i / 10) for i in range(5)]
    svc, _, _ = _service(dense=chunks, context_k=6)
    assert len(svc.retrieve("q", top_k=2).chunks) == 2


def test_empty_corpus_returns_no_chunks_without_raising() -> None:
    svc, _, _ = _service()
    result = svc.retrieve("nothing matches")
    assert result.chunks == ()
    assert result.candidates == ()


def test_pipeline_debug_carries_stage_timings_and_counts() -> None:
    """Spec §12: per-stage timings + candidate counts, persisted per ask."""
    svc, _, _ = _service(dense=[(_chunk("25.1"), 0.5)], lexical=[(_chunk("25.2"), 1.0)])
    debug = svc.retrieve("q").pipeline_debug

    timings = debug["timings_ms"]
    assert isinstance(timings, dict)
    assert {"detect_ms", "dense_ms", "lexical_ms", "clause_ms", "fuse_ms", "rerank_ms"} <= set(
        timings
    )
    counts = debug["counts"]
    assert isinstance(counts, dict)
    assert counts["dense"] == 1 and counts["lexical"] == 1 and counts["fused"] == 2
