"""Unit tests for the retrieval metrics (spec §8). Pure arithmetic."""

from __future__ import annotations

import pytest

from groundcite.services.metrics import (
    first_hit_rank,
    matches,
    mean,
    recall_at_k,
    reciprocal_rank,
)

CP = "14 CFR Part 25 §"


@pytest.mark.parametrize(
    ("retrieved", "expected", "ok"),
    [
        # exact clause
        (f"{CP}25.1309", "25.1309", True),
        # a sub-paragraph IS the clause's text (the chunker splits sections)
        (f"{CP}25.1309(b)", "25.1309", True),
        (f"{CP}25.1309(b)(2)", "25.1309", True),
        # prefix bleed must be impossible
        (f"{CP}25.13099", "25.1309", False),
        (f"{CP}25.130", "25.1309", False),
        (f"{CP}25.1709", "25.1309", False),
        # expected may itself be a full clause_path
        (f"{CP}25.1309(b)", f"{CP}25.1309", True),
    ],
)
def test_clause_matching_rule(retrieved: str, expected: str, ok: bool) -> None:
    assert matches(retrieved, expected) is ok


def test_recall_at_k_respects_the_cutoff() -> None:
    retrieved = [f"{CP}25.999", f"{CP}25.888", f"{CP}25.1309"]
    assert recall_at_k(retrieved, ["25.1309"], k=2) == 0.0
    assert recall_at_k(retrieved, ["25.1309"], k=3) == 1.0


def test_recall_is_fractional_across_multiple_expected_clauses() -> None:
    """A cross-clause synthesis case (spec §8 type 3) expects several clauses."""
    retrieved = [f"{CP}25.1309", f"{CP}25.777"]
    assert recall_at_k(retrieved, ["25.1309", "25.1709"], k=10) == pytest.approx(0.5)
    assert recall_at_k(retrieved, ["25.1309", "25.777"], k=10) == 1.0


def test_reciprocal_rank_uses_the_first_hit() -> None:
    retrieved = [f"{CP}25.999", f"{CP}25.1309", f"{CP}25.1709"]
    assert reciprocal_rank(retrieved, ["25.1309"]) == pytest.approx(1 / 2)
    assert reciprocal_rank([f"{CP}25.1309"], ["25.1309"]) == 1.0
    assert reciprocal_rank([f"{CP}25.999"], ["25.1309"]) == 0.0


def test_first_hit_rank_is_one_based_or_none() -> None:
    retrieved = [f"{CP}25.999", f"{CP}25.1309"]
    assert first_hit_rank(retrieved, ["25.1309"]) == 2
    assert first_hit_rank(retrieved, ["25.404"]) is None


def test_no_expected_clauses_is_unscorable_not_a_zero() -> None:
    """Must-abstain cases carry no expected clause; callers exclude them from the
    mean rather than folding a 0.0 in (which would silently depress recall)."""
    assert recall_at_k([f"{CP}25.1"], [], k=5) == 0.0
    assert reciprocal_rank([f"{CP}25.1"], []) == 0.0
    assert first_hit_rank([f"{CP}25.1"], []) is None


def test_mean_of_empty_is_zero() -> None:
    assert mean([]) == 0.0
    assert mean([1.0, 0.0]) == pytest.approx(0.5)
