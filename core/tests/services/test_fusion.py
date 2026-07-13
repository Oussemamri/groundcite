"""Unit tests for RRF fusion + the clause fast path (spec §7 step 2).

Pure arithmetic — RRF scores are asserted against hand-computed values, not
approximations, because this is the ranking math the whole pipeline rests on.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from groundcite.domain.entities import Chunk
from groundcite.services.fusion import (
    CLAUSE_FAST_PATH_SCORE,
    fuse,
    reciprocal_rank_fusion,
)

RRF_K = 60


def _chunk(clause: str, chunk_id: UUID | None = None) -> Chunk:
    return Chunk(
        id=chunk_id or uuid4(),
        document_id=UUID(int=1),
        section_id=UUID(int=2),
        clause_path=f"14 CFR Part 25 §{clause}",
        content=f"body of {clause}",
        token_count=10,
    )


def test_rrf_score_is_the_spec_formula() -> None:
    """score(c) = Σ 1/(rrf_k + rank_i(c)), ranks 1-based (spec §7 step 2)."""
    a, b = _chunk("25.1"), _chunk("25.2")
    dense = [(a, 0.9), (b, 0.8)]  # a rank 1, b rank 2
    lexical = [(b, 5.0)]  # b rank 1

    scores = reciprocal_rank_fusion([dense, lexical], RRF_K)

    assert scores[a.id] == pytest.approx(1 / 61)
    assert scores[b.id] == pytest.approx(1 / 62 + 1 / 61)


def test_agreement_between_retrievers_outranks_a_single_strong_hit() -> None:
    """The core reason we use RRF: a chunk BOTH retrievers found beats one that
    only a single retriever ranked first."""
    both, dense_only = _chunk("25.both"), _chunk("25.dense")
    dense = [(dense_only, 0.99), (both, 0.10)]  # dense_only rank 1, both rank 2
    lexical = [(both, 9.9)]  # both rank 1

    fused = fuse(dense, lexical, clause_hits=[], rrf_k=RRF_K, top_k=10)

    assert [c.clause_path for c, _ in fused] == [
        "14 CFR Part 25 §25.both",
        "14 CFR Part 25 §25.dense",
    ]
    # 1/62 + 1/61 > 1/61
    assert fused[0][1] == pytest.approx(1 / 62 + 1 / 61)
    assert fused[1][1] == pytest.approx(1 / 61)


def test_clause_fast_path_is_injected_at_rank_one() -> None:
    """An exact clause hit leads, even when fuzzy retrieval loved something else
    (spec §7 step 1c: 'injected at rank 1')."""
    exact = _chunk("25.1309(b)")
    fuzzy_a, fuzzy_b = _chunk("25.aaa"), _chunk("25.bbb")
    dense = [(fuzzy_a, 0.99), (fuzzy_b, 0.98)]
    lexical = [(fuzzy_a, 9.0), (fuzzy_b, 8.0)]

    fused = fuse(dense, lexical, clause_hits=[exact], rrf_k=RRF_K, top_k=10)

    assert fused[0][0].id == exact.id
    assert fused[0][1] == CLAUSE_FAST_PATH_SCORE
    assert fused[0][1] > fused[1][1], "the exact hit must not be outranked by fuzzy agreement"


def test_fast_path_chunk_is_not_duplicated_in_the_tail() -> None:
    """A clause hit that ALSO surfaced in dense/lexical appears exactly once."""
    exact = _chunk("25.1309")
    other = _chunk("25.999")
    dense = [(exact, 0.9), (other, 0.5)]
    lexical = [(exact, 7.0)]

    fused = fuse(dense, lexical, clause_hits=[exact], rrf_k=RRF_K, top_k=10)

    ids = [c.id for c, _ in fused]
    assert ids.count(exact.id) == 1
    assert ids[0] == exact.id
    assert fused[0][1] == CLAUSE_FAST_PATH_SCORE


def test_multiple_fast_path_hits_keep_index_order() -> None:
    """A long clause splits into several chunks; all lead, in index order."""
    c1, c2 = _chunk("25.1309"), _chunk("25.1309")
    fused = fuse([], [], clause_hits=[c1, c2], rrf_k=RRF_K, top_k=10)
    assert [c.id for c, _ in fused] == [c1.id, c2.id]


def test_top_k_truncates_and_zero_is_empty() -> None:
    chunks = [_chunk(f"25.{i}") for i in range(5)]
    dense = [(c, 1.0 - i / 10) for i, c in enumerate(chunks)]

    assert len(fuse(dense, [], [], RRF_K, top_k=3)) == 3
    assert fuse(dense, [], [], RRF_K, top_k=0) == []


def test_empty_inputs_produce_no_candidates() -> None:
    assert fuse([], [], [], RRF_K, top_k=6) == []


def test_ordering_is_deterministic_for_tied_scores() -> None:
    """Equal RRF scores must break ties stably (clause_path, then id), so eval
    runs are reproducible rather than dict-order dependent."""
    a, b = _chunk("25.bbb"), _chunk("25.aaa")
    # Each is rank 1 in a different list → identical RRF scores.
    first = fuse([(a, 0.9)], [(b, 9.0)], [], RRF_K, top_k=10)
    second = fuse([(a, 0.9)], [(b, 9.0)], [], RRF_K, top_k=10)

    assert first[0][1] == pytest.approx(first[1][1]), "precondition: scores are tied"
    assert [c.clause_path for c, _ in first] == [c.clause_path for c, _ in second]
    assert [c.clause_path for c, _ in first] == [
        "14 CFR Part 25 §25.aaa",
        "14 CFR Part 25 §25.bbb",
    ]
