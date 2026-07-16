"""Unit tests for the Week 5 AD-2 eval-case read extension. Fake ports only
(rule 3): ``EvalService.get_cases`` (thin Repository delegate, mirrors
``list_runs``) and ``FakeRepository.get_eval_cases`` (the case join the
`/evals` drill-down needs -- eval_results stores metrics keyed by case_id but
not the Case's own fields)."""

from __future__ import annotations

from uuid import uuid4

from groundcite.domain.entities import EvalCase
from groundcite.domain.results import EvalRun
from groundcite.services.ask import AskService
from groundcite.services.eval import EvalService
from tests.fakes import FakeEmbedder, FakeLexicalIndex, FakeRepository, FakeVectorIndex


def _case(question: str = "What does §25.1309(b) require?") -> EvalCase:
    return EvalCase(
        id=uuid4(),
        suite="core",
        question=question,
        expected_clauses=("14 CFR Part 25 §25.1309(b)",),
        must_abstain=False,
        language="en",
    )


def _evals(repository: FakeRepository | None) -> EvalService:
    ask = AskService(
        embedder=FakeEmbedder(),
        vector_index=FakeVectorIndex([]),
        lexical_index=FakeLexicalIndex(),
    )
    return EvalService(ask=ask, load_suite=lambda _suite: [], repository=repository)


def test_fake_repository_get_eval_cases_returns_known_ids() -> None:
    repo = FakeRepository()
    c1, c2 = _case("q1"), _case("q2")
    repo.eval_cases[c1.id] = c1
    repo.eval_cases[c2.id] = c2

    got = repo.get_eval_cases([c1.id, c2.id])

    assert got[c1.id].question == "q1"
    assert got[c2.id].question == "q2"


def test_fake_repository_get_eval_cases_drops_unknown_ids() -> None:
    repo = FakeRepository()
    known = _case("known")
    repo.eval_cases[known.id] = known
    unknown_id = uuid4()

    got = repo.get_eval_cases([known.id, unknown_id])

    assert set(got) == {known.id}


def test_fake_repository_get_eval_cases_empty_input() -> None:
    repo = FakeRepository()
    assert repo.get_eval_cases([]) == {}


def test_eval_service_get_cases_delegates_to_repository() -> None:
    repo = FakeRepository()
    case = _case()
    repo.eval_cases[case.id] = case

    got = _evals(repo).get_cases([case.id])

    assert got[case.id] is case


def test_eval_service_get_cases_no_repository_returns_empty() -> None:
    assert _evals(None).get_cases([uuid4()]) == {}


def test_eval_service_list_runs_and_get_report_expose_started_at_and_suite_fields() -> None:
    # FakeRepository doesn't derive started_at/suite (that's a pg-level SQL
    # join, verified live -- AD-2); this confirms the domain fields exist and
    # round-trip through the fake unharmed (default None), so nothing in the
    # read path silently drops them for adapters that DO populate them.
    repo = FakeRepository()
    run = EvalRun(id=uuid4(), git_sha="abc123", config={"tau_retrieval": 0.7})
    repo.eval_runs[run.id] = run
    repo.eval_results[run.id] = []
    service = _evals(repo)

    runs = service.list_runs()
    report = service.get_report(run.id)

    assert runs[0].started_at is None
    assert runs[0].suite is None
    assert report is not None
    got_run, results = report
    assert got_run.id == run.id
    assert results == []
