"""Unit test for the generic 500 fallback handler (spec §9, §12; AD-6, AD-9).

Distinct from ``/healthz``'s DB check (test_health.py), which catches the same
kind of failure and converts it to a controlled 503 -- this exercises a route
with NO try/except, so an unexpected exception falls through to the generic
``Exception`` handler and must come back as a 500 problem+json with no leaked
internals, while still being logged server-side (structlog `unhandled_exception`).

Uses a raw ``TestClient(app, raise_server_exceptions=False)`` rather than the
shared ``make_client`` fixture: Starlette's TestClient re-raises unhandled
server exceptions by default (a deliberate "don't silently miss a 500 in
tests" signal) -- exactly right for every OTHER test here, but this test's
whole point is to observe the response the fallback handler actually
produces, so that default must be turned off for this one client.

The logging assertion mocks ``app.errors.get_logger`` rather than capturing
real stdout: structlog is configured with ``cache_logger_on_first_use=True``
(logging_conf.py), so whichever test runs first in the process binds the
logger to ITS OWN stdout/capsys snapshot -- every later test's capsys then
observes nothing, even though the write genuinely happened. Mocking the
logger call sidesteps that capture-timing fragility entirely."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.deps import get_app_settings, get_services
from app.main import create_app
from tests.conftest import StubServices, StubSettings


def _non_raising_client(stub_services: StubServices) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_services] = lambda: stub_services
    app.dependency_overrides[get_app_settings] = lambda: StubSettings()
    app.state.services = stub_services
    return TestClient(app, raise_server_exceptions=False)


def test_unhandled_exception_returns_500_problem_json_without_leaking_detail(
    stub_services: StubServices,
) -> None:
    stub_services.library.list_documents_error = RuntimeError("credentials=supersecret")
    r = _non_raising_client(stub_services).get("/api/v1/documents")
    assert r.status_code == 500
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["type"] == "https://groundcite.dev/problems/internal-error"
    assert body["title"] == "Internal Server Error"
    assert body["status"] == 500
    assert body["detail"] is None  # never surface the raw exception message
    assert "credentials" not in r.text and "supersecret" not in r.text
    assert "instance" in body


def test_unhandled_exception_is_logged(stub_services: StubServices) -> None:
    stub_services.library.list_documents_error = RuntimeError("boom")
    mock_logger = MagicMock()
    with patch("app.errors.get_logger", return_value=mock_logger) as mock_get_logger:
        _non_raising_client(stub_services).get("/api/v1/documents")
    mock_get_logger.assert_called_once_with("app.errors")
    mock_logger.exception.assert_called_once_with("unhandled_exception", error="boom")
