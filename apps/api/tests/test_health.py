"""Unit tests for ``/healthz`` (spec §9, §12; AD-9)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_healthz_ok(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["checks"] == {"db": "ok"}
    # Residual #4: drift visible from one request.
    cfg = body["config"]
    assert cfg["tau_retrieval"] == 0.70
    assert cfg["groq_model"] == "openai/gpt-oss-120b"
    assert "llm_provider" in cfg and "reranker_enabled" in cfg


def test_healthz_db_failure_returns_503_problem_json(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    stub_services.library.list_documents_error = RuntimeError("connection refused")
    c = make_client(stub_services)
    r = c.get("/healthz")
    assert r.status_code == 503
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["type"] == "https://groundcite.dev/problems/unhealthy"
    assert body["title"] == "Service Unavailable"
    assert "db" in body["detail"]
    assert body["status"] == 503
