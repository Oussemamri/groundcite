"""Unit tests for ``GET /eval/runs`` and ``GET /eval/runs/{id}`` (spec §9)."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from groundcite.domain.results import EvalResult, EvalRun


def _run(rid: UUID, sha: str = "19de5cd") -> EvalRun:
    return EvalRun(id=rid, git_sha=sha, config={"tau_retrieval": 0.70})


def _result(run_id: UUID, case_id: UUID) -> EvalResult:
    return EvalResult(
        run_id=run_id,
        case_id=case_id,
        recall_at_5=0.86,
        recall_at_10=0.90,
        mrr=0.85,
        citation_precision=0.88,
        passed=True,
        debug={"status": "grounded"},
    )


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


def test_get_eval_run_unknown_404(client: TestClient) -> None:
    r = client.get(f"/api/v1/eval/runs/{uuid4()}")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["type"] == "https://groundcite.dev/problems/not-found"


def test_get_eval_run_malformed_id_404(client: TestClient) -> None:
    assert client.get("/api/v1/eval/runs/not-a-uuid").status_code == 404
