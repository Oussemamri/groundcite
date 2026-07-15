"""Unit tests for EvalService.run_full (spec §8, Phase 5). Fake ports only.

Covers the judge-adjacent metrics run_retrieval does NOT: citation_precision
and abstention correctness, both driven through the real Gates A/B via
AskService.ask (with a FakeLLM/FakeReranker so no network/model is touched).
"""

from __future__ import annotations

from uuid import UUID, uuid4

from groundcite.domain.entities import Chunk, EvalCase
from groundcite.domain.results import AbstentionReason, AskStatus
from groundcite.services.ask import AskService
from groundcite.services.eval import EvalService
from tests.fakes import (
    FakeEmbedder,
    FakeLexicalIndex,
    FakeLLM,
    FakeRepository,
    FakeReranker,
    FakeVectorIndex,
)


def _chunk(clause: str) -> Chunk:
    return Chunk(
        id=uuid4(),
        document_id=UUID(int=1),
        section_id=UUID(int=2),
        clause_path=f"14 CFR Part 25 §{clause}",
        content=f"body of {clause}",
        token_count=10,
    )


def _case(
    question: str,
    expected: tuple[str, ...] = (),
    must_abstain: bool = False,
) -> EvalCase:
    return EvalCase(
        id=uuid4(),
        suite="core",
        question=question,
        expected_clauses=expected,
        must_abstain=must_abstain,
    )


def _valid_json(chunk: Chunk, answer: str = "The answer.") -> str:
    return (
        f'{{"answer_md": "{answer}", "citations": '
        f'[{{"chunk_id": "{chunk.id}", "claim": "grounding claim"}}], "insufficient": false}}'
    )


def _evals(
    dense: list[tuple[Chunk, float]],
    cases: list[EvalCase],
    reranker_scores: dict[str, float] | None = None,
    llm_responses: str | list[str] | None = None,
    repository: FakeRepository | None = False,  # type: ignore[assignment]
    tau_retrieval: float = 0.35,
) -> tuple[EvalService, FakeRepository | None]:
    repo: FakeRepository | None = FakeRepository() if repository is False else repository
    ask = AskService(
        embedder=FakeEmbedder(),
        vector_index=FakeVectorIndex(dense),
        lexical_index=FakeLexicalIndex(),
        reranker=FakeReranker(reranker_scores or {}),
        llm=FakeLLM(llm_responses) if llm_responses is not None else None,
        tau_retrieval=tau_retrieval,
        repository=repo,
    )
    evals = EvalService(ask=ask, load_suite=lambda _s: cases, repository=repo)
    return evals, repo


def test_grounded_case_with_correct_citation_scores_full_precision() -> None:
    c = _chunk("25.1309(b)")
    case = _case("What does §25.1309(b) require?", expected=("25.1309",))
    evals, repo = _evals(
        dense=[(c, 0.9)],
        cases=[case],
        reranker_scores={c.clause_path: 0.9},
        llm_responses=_valid_json(c),
    )
    report, run_id = evals.run_full("core")

    assert report.total_cases == 1
    assert report.grounded_cases == 1
    assert report.abstained_cases == 0
    assert report.mean_citation_precision == 1.0
    assert report.abstention_accuracy == 1.0  # correctly did NOT abstain
    assert report.cases[0].status is AskStatus.GROUNDED
    assert report.cases[0].abstention_correct is True

    assert repo is not None
    assert repo.eval_runs[run_id].id == run_id
    rows = repo.eval_results[run_id]
    assert len(rows) == 1
    assert rows[0].citation_precision == 1.0
    assert rows[0].passed is True
    assert rows[0].abstained is False
    assert rows[0].faithfulness is None, "no judge configured — never fabricated"


def test_grounded_case_with_off_target_citation_scores_partial_precision() -> None:
    cited, other = _chunk("25.999"), _chunk("25.1309")
    case = _case("q?", expected=("25.1309",))
    evals, _ = _evals(
        dense=[(cited, 0.9)],
        cases=[case],
        reranker_scores={cited.clause_path: 0.9},
        llm_responses=_valid_json(cited),  # cites the WRONG (irrelevant) chunk
    )
    report, _ = evals.run_full("core")
    assert report.cases[0].citation_precision == 0.0
    del other  # unused beyond documenting intent


def test_must_abstain_case_correctly_abstaining_scores_accurate() -> None:
    c = _chunk("25.999")
    case = _case("What does DO-178C say about MC/DC?", must_abstain=True)
    evals, repo = _evals(
        dense=[(c, 0.9)],
        cases=[case],
        reranker_scores={c.clause_path: 0.05},  # below tau -> Gate A abstains
        llm_responses="unreachable",
    )
    report, run_id = evals.run_full("core")

    assert report.abstained_cases == 1
    assert report.abstention_accuracy == 1.0
    assert report.cases[0].abstention_correct is True
    assert report.cases[0].citation_precision is None, "nothing was cited"
    assert report.cases[0].abstention_reason is AbstentionReason.WEAK_RETRIEVAL

    assert repo is not None
    row = repo.eval_results[run_id][0]
    assert row.abstained is True
    assert row.citation_precision is None


def test_must_abstain_case_that_answers_anyway_is_scored_wrong() -> None:
    """The hallucination-risk case (§1): a should-abstain question that the
    pipeline answered anyway must be flagged incorrect, not silently passed."""
    c = _chunk("25.1309(b)")
    case = _case("out of corpus but retrieval accidentally scores high", must_abstain=True)
    evals, _ = _evals(
        dense=[(c, 0.9)],
        cases=[case],
        reranker_scores={c.clause_path: 0.95},  # clears tau — pipeline WILL answer
        llm_responses=_valid_json(c),
    )
    report, _ = evals.run_full("core")

    assert report.cases[0].status is AskStatus.GROUNDED
    assert report.cases[0].abstention_correct is False
    assert report.abstention_accuracy == 0.0


def test_grounded_case_that_wrongly_abstains_is_scored_wrong() -> None:
    c = _chunk("25.999")
    case = _case("a real question", expected=("25.1309",), must_abstain=False)
    evals, _ = _evals(
        dense=[(c, 0.9)],
        cases=[case],
        reranker_scores={c.clause_path: 0.05},  # below tau -> abstains
        llm_responses="unreachable",
    )
    report, _ = evals.run_full("core")

    assert report.cases[0].status is AskStatus.ABSTAINED
    assert report.cases[0].abstention_correct is False
    assert report.abstention_accuracy == 0.0


def test_report_aggregates_counts_across_multiple_cases() -> None:
    """Two cases through the SAME AskService necessarily see identical
    retrieval (FakeVectorIndex/FakeEmbedder do not vary by question text) —
    so this checks the aggregation arithmetic (counts, means) sums correctly
    across >1 case, not per-case gate differentiation (covered by the
    single-case tests above)."""
    c = _chunk("25.1309(b)")
    cases = [
        _case("q1", expected=("25.1309",)),
        _case("q2", expected=("25.1309",)),
    ]
    evals, _ = _evals(
        dense=[(c, 0.9)],
        cases=cases,
        reranker_scores={c.clause_path: 0.9},
        llm_responses=_valid_json(c),
    )
    report, _ = evals.run_full("core")

    assert report.total_cases == 2
    assert report.grounded_cases == 2
    assert report.abstained_cases == 0
    assert report.error_cases == 0
    assert report.abstention_accuracy == 1.0
    assert report.mean_citation_precision == 1.0
    assert len(report.cases) == 2


def test_judge_flag_is_recorded_but_faithfulness_stays_null() -> None:
    """AD-7: no second provider is configured this week — --judge must not
    fabricate a faithfulness score, and the run still completes."""
    c = _chunk("25.1309(b)")
    case = _case("q?", expected=("25.1309",))
    evals, _ = _evals(
        dense=[(c, 0.9)],
        cases=[case],
        reranker_scores={c.clause_path: 0.9},
        llm_responses=_valid_json(c),
    )
    report, _ = evals.run_full("core", judge=True)
    assert report.judge is True
    assert report.mean_faithfulness is None
    assert report.cases[0].faithfulness is None


def test_persistence_is_skipped_when_no_repository_wired() -> None:
    c = _chunk("25.1309(b)")
    case = _case("q?", expected=("25.1309",))
    evals, repo = _evals(
        dense=[(c, 0.9)],
        cases=[case],
        reranker_scores={c.clause_path: 0.9},
        llm_responses=_valid_json(c),
        repository=None,
    )
    assert repo is None
    report, run_id = evals.run_full("core")  # must not raise
    assert report.total_cases == 1
    assert run_id is not None


def test_run_id_is_stable_across_the_run_and_config_is_snapshotted() -> None:
    c = _chunk("25.1")
    case = _case("q?", expected=("25.1",))
    evals, repo = _evals(
        dense=[(c, 0.9)],
        cases=[case],
        reranker_scores={c.clause_path: 0.9},
        llm_responses=_valid_json(c),
    )
    report, run_id = evals.run_full("core", git_sha="abc1234", config={"rrf_k": 60})
    assert report.git_sha == "abc1234"
    assert report.config == {"rrf_k": 60}
    assert repo is not None
    assert repo.eval_runs[run_id].git_sha == "abc1234"
    assert repo.eval_runs[run_id].config == {"rrf_k": 60}
