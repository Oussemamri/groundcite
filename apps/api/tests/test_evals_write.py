"""Unit tests for ``POST /api/v1/eval/runs`` (spec §9; AD-5).

Same POST-then-GET pattern as test_documents_write.py: the 202 response
reflects the "queued" job snapshot taken before the BackgroundTask runs;
the real outcome is read back via GET /jobs/{id}."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from groundcite.domain.results import EvalRun, FullEvalReport, RetrievalEvalReport


def _full_report(**overrides: object) -> FullEvalReport:
    defaults: dict[str, object] = {
        "suite": "core",
        "git_sha": "abc1234",
        "judge": False,
        "total_cases": 40,
        "grounded_cases": 36,
        "abstained_cases": 4,
        "error_cases": 0,
        "abstention_accuracy": 0.9,
        "mean_citation_precision": 0.885,
    }
    defaults.update(overrides)
    return FullEvalReport(**defaults)  # type: ignore[arg-type]


def _retrieval_report(**overrides: object) -> RetrievalEvalReport:
    defaults: dict[str, object] = {
        "suite": "core",
        "git_sha": "abc1234",
        "reranked": True,
        "scored_cases": 40,
        "must_abstain_cases": 0,
        "recall_at_5": 0.863,
        "recall_at_10": 0.902,
        "mrr": 0.850,
    }
    defaults.update(overrides)
    return RetrievalEvalReport(**defaults)  # type: ignore[arg-type]


def test_trigger_full_run_returns_202_queued_job(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    run_id = uuid4()
    stub_services.evals.full_result = (_full_report(), run_id)
    r = make_client(stub_services).post("/api/v1/eval/runs", json={"suite": "core", "full": True})
    assert r.status_code == 202
    body = r.json()
    assert body["kind"] == "eval_run"
    assert body["status"] == "queued"


def test_trigger_full_run_completes_with_run_id(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    run_id = uuid4()
    stub_services.evals.full_result = (_full_report(grounded_cases=36), run_id)
    c = make_client(stub_services)
    job_id = c.post("/api/v1/eval/runs", json={"suite": "core", "full": True}).json()["id"]
    body = c.get(f"/api/v1/jobs/{job_id}").json()
    assert body["status"] == "done"
    assert body["result"]["run_id"] == str(run_id)
    assert body["result"]["total_cases"] == 40
    assert body["result"]["grounded_cases"] == 36


def test_trigger_retrieval_only_run_has_no_run_id(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    # run_retrieval never persists (spec §15.1) -- no eval_runs row, no id.
    stub_services.evals.retrieval_result = _retrieval_report()
    c = make_client(stub_services)
    job_id = c.post("/api/v1/eval/runs", json={"suite": "core", "full": False}).json()["id"]
    body = c.get(f"/api/v1/jobs/{job_id}").json()
    assert body["status"] == "done"
    assert body["result"]["run_id"] is None
    assert body["result"]["scored_cases"] == 40
    assert body["result"]["recall_at_5"] == 0.863


def test_trigger_run_defaults_to_retrieval_only(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    stub_services.evals.retrieval_result = _retrieval_report()
    c = make_client(stub_services)
    job_id = c.post("/api/v1/eval/runs", json={"suite": "core"}).json()["id"]
    body = c.get(f"/api/v1/jobs/{job_id}").json()
    assert body["result"]["full"] is False


def test_trigger_run_failure_marks_job_error(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    stub_services.evals.run_error = RuntimeError("suite 'bogus' not found")
    c = make_client(stub_services)
    job_id = c.post("/api/v1/eval/runs", json={"suite": "bogus", "full": True}).json()["id"]
    body = c.get(f"/api/v1/jobs/{job_id}").json()
    assert body["status"] == "error"
    assert "bogus" in body["detail"]


def test_trigger_run_rejects_unknown_fields(client: TestClient) -> None:
    r = client.post("/api/v1/eval/runs", json={"suite": "core", "bogus": 1})
    assert r.status_code == 422


def test_trigger_run_requires_suite(client: TestClient) -> None:
    r = client.post("/api/v1/eval/runs", json={})
    assert r.status_code == 422


def test_list_eval_runs_still_works(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    # Confirms the write route didn't disturb the pre-existing read routes.
    stub_services.evals.runs = [EvalRun(id=uuid4(), git_sha="abc1234", config={})]
    r = make_client(stub_services).get("/api/v1/eval/runs")
    assert r.status_code == 200
    assert len(r.json()) == 1
