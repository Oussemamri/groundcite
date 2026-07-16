"""Unit tests for ``GET /api/v1/jobs/{id}`` (spec §9; AD-5).

The happy path (a real job reaching "done"/"error") is covered indirectly
by test_documents_write.py / test_evals_write.py, which are the only
routes that actually CREATE jobs -- this file covers this route's own
edge cases in isolation."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient


def test_get_unknown_job_404_problem_json(client: TestClient) -> None:
    r = client.get(f"/api/v1/jobs/{uuid4()}")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["type"] == "https://groundcite.dev/problems/not-found"
    assert "job" in body["detail"]


def test_get_malformed_job_id_404_not_422(client: TestClient) -> None:
    r = client.get("/api/v1/jobs/not-a-uuid")
    assert r.status_code == 404
