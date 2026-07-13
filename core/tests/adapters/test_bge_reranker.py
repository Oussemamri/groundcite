"""Tests for the bge_reranker adapter (spec §7 step 3, §11).

The pure normalization is unit-tested (no model). The real cross-encoder is
exercised only when the `rerank` extra is installed — it is skipped otherwise, so
CI (no extras) stays green.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from groundcite.adapters.reranker.bge_reranker import _normalize, make_bge_reranker
from groundcite.domain.entities import Chunk


def _chunk(clause: str, content: str) -> Chunk:
    return Chunk(
        id=uuid4(),
        document_id=UUID(int=1),
        section_id=UUID(int=2),
        clause_path=f"14 CFR Part 25 §{clause}",
        content=content,
        token_count=10,
    )


def test_normalize_maps_logits_into_the_unit_interval() -> None:
    """The cross-encoder emits raw logits (measured on bge-reranker-v2-m3: 2.40,
    1.86, 1.47). Shipping those raw would break Gate A — every passage would clear
    τ=0.35 on an unbounded scale (spec §11 wants normalized scores)."""
    for logit in (-12.0, -1.0, 0.0, 1.4738, 1.8620, 2.4003, 12.0):
        assert 0.0 < _normalize(logit) < 1.0

    assert _normalize(0.0) == pytest.approx(0.5)
    assert _normalize(2.4003) == pytest.approx(0.9168, abs=1e-3)


def test_normalize_is_strictly_monotonic() -> None:
    """Order is the cross-encoder's judgement; normalization must not reorder."""
    logits = [-3.0, -0.5, 0.0, 0.5, 1.4738, 1.8620, 2.4003]
    scores = [_normalize(x) for x in logits]
    assert scores == sorted(scores)


def test_empty_or_zero_top_k_short_circuits_without_loading_a_model() -> None:
    reranker = make_bge_reranker()
    assert reranker.rerank("q", [], top_k=6) == []
    assert reranker.rerank("q", [_chunk("25.1", "text")], top_k=0) == []


@pytest.mark.integration
def test_real_cross_encoder_ranks_the_relevant_clause_first() -> None:
    """Runs the actual bge-reranker-v2-m3. Skipped unless the rerank extra is
    installed (CI installs no extras)."""
    pytest.importorskip("rerankers")

    candidates = [
        _chunk("25.777", "Each cockpit control must be located to provide convenient operation."),
        _chunk(
            "25.1309(b)",
            "The airplane systems must be designed so that the occurrence of any "
            "catastrophic failure condition is extremely improbable.",
        ),
        _chunk("25.981", "Fuel tank ignition prevention requirements."),
    ]
    ranked = make_bge_reranker().rerank(
        "What failure probability is acceptable for catastrophic conditions?",
        candidates,
        top_k=3,
    )

    assert ranked[0][0].clause_path == "14 CFR Part 25 §25.1309(b)"
    scores = [s for _, s in ranked]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 < s < 1.0 for s in scores), "scores must be normalized (spec §11)"
