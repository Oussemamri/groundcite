"""Unit tests for ``GET /eval/runs`` and ``GET /eval/runs/{id}`` (spec §9)."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from groundcite.domain.entities import EvalCase
from groundcite.domain.results import EvalResult, EvalRun


def _run(rid: UUID, sha: str = "19de5cd") -> EvalRun:
    return EvalRun(id=rid, git_sha=sha, config={"tau_retrieval": 0.70})


def _result(run_id: UUID, case_id: UUID, **overrides: object) -> EvalResult:
    base: dict[str, object] = {
        "run_id": run_id,
        "case_id": case_id,
        "recall_at_5": 0.86,
        "recall_at_10": 0.90,
        "mrr": 0.85,
        "citation_precision": 0.88,
        "passed": True,
        "debug": {"status": "grounded"},
    }
    base.update(overrides)
    return EvalResult(**base)  # type: ignore[arg-type]


def _case(cid: UUID, **overrides: object) -> EvalCase:
    base: dict[str, object] = {
        "id": cid,
        "suite": "core",
        "question": "What does §25.1309(b) require?",
        "expected_clauses": ("14 CFR Part 25 §25.1309(b)",),
        "must_abstain": False,
        "language": "en",
    }
    base.update(overrides)
    return EvalCase(**base)  # type: ignore[arg-type]


def test_list_eval_runs_empty(client: TestClient) -> None:
    assert client.get("/api/v1/eval/runs").json() == []


def test_list_eval_runs_returns_newest_first(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    r1, r2 = _run(uuid4(), "aaa"), _run(uuid4(), "bbb")
    stub_services.evals.runs = [r1, r2]  # stub returns the list as-is (service orders)
    body = make_client(stub_services).get("/api/v1/eval/runs").json()
    assert [b["git_sha"] for b in body] == ["aaa", "bbb"]
    assert "config" in body[0]


def test_get_eval_run_detail_ok(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    rid, cid = uuid4(), uuid4()
    run = _run(rid)
    res = _result(rid, cid)
    stub_services.evals.reports = {rid: (run, [res])}
    body = make_client(stub_services).get(f"/api/v1/eval/runs/{rid}").json()
    assert body["run"]["git_sha"] == "19de5cd"
    assert body["results"][0]["recall_at_5"] == 0.86
    assert body["results"][0]["passed"] is True


def test_get_eval_run_detail_joins_case_metadata(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    """AD-2: the drill-down needs question/expected_clauses/must_abstain from
    eval_cases, joined onto the per-case metric row by case_id."""
    rid, cid = uuid4(), uuid4()
    run = _run(rid)
    res = _result(rid, cid)
    case = _case(cid, question="What does §25.1309(b) require?", must_abstain=False)
    stub_services.evals.reports = {rid: (run, [res])}
    stub_services.evals.cases = {cid: case}

    body = make_client(stub_services).get(f"/api/v1/eval/runs/{rid}").json()

    result = body["results"][0]
    assert result["question"] == "What does §25.1309(b) require?"
    assert result["expected_clauses"] == ["14 CFR Part 25 §25.1309(b)"]
    assert result["must_abstain"] is False
    assert result["language"] == "en"


def test_get_eval_run_detail_unknown_case_id_leaves_metadata_none(  # type: ignore[no-untyped-def]
    make_client, stub_services
) -> None:
    """A case id with no matching eval_cases row (should not happen for a real
    run, but never silently fabricated) leaves the metadata fields None."""
    rid, cid = uuid4(), uuid4()
    run = _run(rid)
    res = _result(rid, cid)
    stub_services.evals.reports = {rid: (run, [res])}
    # stub_services.evals.cases left empty -- cid is "unknown"

    body = make_client(stub_services).get(f"/api/v1/eval/runs/{rid}").json()

    result = body["results"][0]
    assert result["question"] is None
    assert result["expected_clauses"] == []
    assert result["must_abstain"] is None


def test_get_eval_run_detail_aggregates_computed_from_results(  # type: ignore[no-untyped-def]
    make_client, stub_services
) -> None:
    """AD-2: aggregates are computed HERE from the persisted per-case rows,
    never by re-running -- hand-computed fixture, two cases."""
    rid = uuid4()
    cid1, cid2 = uuid4(), uuid4()
    run = _run(rid)
    res1 = _result(rid, cid1, recall_at_5=1.0, recall_at_10=1.0, mrr=1.0, passed=True)
    res2 = _result(
        rid, cid2, recall_at_5=0.0, recall_at_10=0.5, mrr=0.5, citation_precision=None, passed=False
    )
    stub_services.evals.reports = {rid: (run, [res1, res2])}

    body = make_client(stub_services).get(f"/api/v1/eval/runs/{rid}").json()

    agg = body["aggregates"]
    assert agg["scored_cases"] == 2
    assert agg["mean_recall_at_5"] == 0.5
    assert agg["mean_recall_at_10"] == 0.75
    assert agg["mean_mrr"] == 0.75
    assert agg["mean_citation_precision"] == 0.88  # only res1 has a value
    assert agg["abstention_accuracy"] == 0.5  # one passed, one didn't


def test_list_eval_runs_carries_started_at_and_suite(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    from datetime import UTC, datetime

    run = EvalRun(
        id=uuid4(),
        git_sha="19de5cd",
        config={},
        started_at=datetime(2026, 7, 16, tzinfo=UTC),
        suite="core",
    )
    stub_services.evals.runs = [run]
    body = make_client(stub_services).get("/api/v1/eval/runs").json()
    assert body[0]["suite"] == "core"
    assert body[0]["started_at"] is not None


def test_get_eval_run_unknown_404(client: TestClient) -> None:
    r = client.get(f"/api/v1/eval/runs/{uuid4()}")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["type"] == "https://groundcite.dev/problems/not-found"


def test_get_eval_run_malformed_id_404(client: TestClient) -> None:
    assert client.get("/api/v1/eval/runs/not-a-uuid").status_code == 404
