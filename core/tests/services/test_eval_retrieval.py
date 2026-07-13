"""Unit tests for EvalService.run_retrieval (spec §8, §15.1). Fake ports only."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from groundcite.domain.entities import Chunk, EvalCase
from groundcite.services.ask import AskService
from groundcite.services.eval import EvalService
from tests.fakes import FakeEmbedder, FakeLexicalIndex, FakeVectorIndex


def _chunk(clause: str) -> Chunk:
    return Chunk(
        id=uuid4(),
        document_id=UUID(int=1),
        section_id=UUID(int=2),
        clause_path=f"14 CFR Part 25 §{clause}",
        content=f"body of {clause}",
        token_count=10,
    )


def _case(question: str, expected: tuple[str, ...], must_abstain: bool = False) -> EvalCase:
    return EvalCase(
        id=uuid4(),
        suite="core",
        question=question,
        expected_clauses=expected,
        must_abstain=must_abstain,
    )


def _evals(dense: list[tuple[Chunk, float]], cases: list[EvalCase]) -> EvalService:
    ask = AskService(
        embedder=FakeEmbedder(),
        vector_index=FakeVectorIndex(dense),
        lexical_index=FakeLexicalIndex(),
    )
    return EvalService(ask=ask, load_suite=lambda _suite: cases)


def test_scores_a_hit_at_rank_one() -> None:
    dense = [(_chunk("25.1309"), 0.9), (_chunk("25.999"), 0.1)]
    report = _evals(dense, [_case("q", ("25.1309",))]).run_retrieval("core")

    assert report.scored_cases == 1
    assert report.recall_at_5 == 1.0
    assert report.recall_at_10 == 1.0
    assert report.mrr == 1.0
    assert report.cases[0].first_hit_rank == 1


def test_scores_a_complete_miss_as_zero() -> None:
    dense = [(_chunk("25.999"), 0.9)]
    report = _evals(dense, [_case("q", ("25.1309",))]).run_retrieval("core")

    assert report.recall_at_5 == 0.0
    assert report.mrr == 0.0
    assert report.cases[0].first_hit_rank is None


def test_must_abstain_cases_are_excluded_from_the_means() -> None:
    """A negative case has no expected clause. Folding its unavoidable 0.0 into
    recall would misreport the retriever — abstention is Gate A (Week 3)."""
    dense = [(_chunk("25.1309"), 0.9)]
    cases = [
        _case("grounded", ("25.1309",)),
        _case("What does DO-178C say about MC/DC?", (), must_abstain=True),
    ]
    report = _evals(dense, cases).run_retrieval("core")

    assert report.scored_cases == 1, "only the grounded case is scorable"
    assert report.must_abstain_cases == 1
    assert report.recall_at_5 == 1.0, "the must-abstain case must not drag recall to 0.5"
    assert len(report.cases) == 2, "but it is still reported"


def test_must_abstain_case_records_its_top_score_for_tau_tuning() -> None:
    """The score a must-abstain case reaches is the evidence for setting
    τ_retrieval in Gate A (Week 3), so it is captured even though it is unscored.

    NOTE the score recorded is the FUSED score, not the retriever's raw score —
    that is the number Gate A actually compares against τ. With the reranker off
    a rank-1 hit in one list scores 1/(rrf_k+1) = 1/61 ≈ 0.0164, which is what
    makes the spec's "RRF ≥ 0.05" threshold unreachable (see test below).
    """
    dense = [(_chunk("25.999"), 0.42)]  # raw dense score, discarded by RRF
    cases = [_case("out of corpus", (), must_abstain=True)]
    report = _evals(dense, cases).run_retrieval("core")

    assert report.cases[0].top_score == pytest.approx(1 / 61)


def test_rrf_ceiling_is_below_the_specs_tau_of_0_05() -> None:
    """Guards a real inconsistency found by the first baseline (spec §7 defaults):
    with rrf_k=60 and TWO candidate lists, the maximum attainable RRF score is
    2/(60+1) = 0.0328 — BELOW the spec's reranker-off τ_retrieval of 0.05. Gate A
    (Week 3) would therefore abstain on every semantic question that the clause
    fast path (score 1.0) does not rescue. Week 3 must either lower τ for the
    RRF path, normalize RRF, or require the reranker. Pinned here so the
    arithmetic cannot silently drift."""
    hit = _chunk("25.1309")
    ask = AskService(
        embedder=FakeEmbedder(),
        vector_index=FakeVectorIndex([(hit, 0.99)]),
        lexical_index=FakeLexicalIndex([(hit, 9.9)]),  # rank 1 in BOTH lists
    )
    result = ask.retrieve("best possible fused score")

    assert result.chunks[0].score == pytest.approx(2 / 61)
    assert result.chunks[0].score < 0.05


def test_recall_at_10_can_exceed_recall_at_5() -> None:
    """The eval retrieves 10 candidates, so a hit at rank 7 counts for @10 only."""
    dense = [(_chunk(f"25.{i}"), 1.0 - i / 100) for i in range(6)]
    dense.append((_chunk("25.1309"), 0.3))  # rank 7
    report = _evals(dense, [_case("q", ("25.1309",))]).run_retrieval("core")

    assert report.recall_at_5 == 0.0
    assert report.recall_at_10 == 1.0
    assert report.mrr == pytest.approx(1 / 7)


def test_report_carries_sha_and_config_snapshot() -> None:
    """Spec §8: the config snapshot must be stored so runs stay comparable."""
    report = _evals([], [_case("q", ("25.1",))]).run_retrieval(
        "core", git_sha="abc1234", config={"rrf_k": 60}
    )
    assert report.git_sha == "abc1234"
    assert report.config == {"rrf_k": 60}
    assert report.suite == "core"
