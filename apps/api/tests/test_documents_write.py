"""Unit tests for ``POST /api/v1/documents`` (spec §9, §13; AD-5).

The POST response reflects the job at the moment it's created (status
"queued") -- it is built and serialized BEFORE the scheduled BackgroundTask
runs, even though that task completes before ``.post()`` returns control to
the test (Starlette's TestClient runs BackgroundTasks synchronously,
verified empirically). So the real assertion on outcome is a follow-up
``GET /jobs/{id}`` on the SAME client, which reads the job's now-mutated
state -- this is also the intended real-world polling contract (spec §9:
202 + job_id, then GET /jobs/{id})."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from groundcite.domain.results import IngestionReport


def _pdf_bytes() -> bytes:
    return b"%PDF-1.4 fake pdf content for a stub ingestion service\n"


def _form_fields(**overrides: str) -> dict[str, str]:
    fields = {
        "slug": "test-doc",
        "standard_code": "14 CFR Part 25",
        "title": "Test Standard",
        "organization": "FAA",
        "license_note": "US public domain",
    }
    fields.update(overrides)
    return fields


def _report(**overrides: object) -> IngestionReport:
    defaults: dict[str, object] = {
        "slug": "test-doc",
        "standard_code": "14 CFR Part 25",
        "sections_found": 10,
        "chunks_created": 42,
        "orphan_pct": 0.02,
        "attached_pct": 0.98,
        "total_text_chars": 12345,
        "document_id": uuid4(),
    }
    defaults.update(overrides)
    return IngestionReport(**defaults)  # type: ignore[arg-type]


def test_upload_document_returns_202_queued_job(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    stub_services.ingestion.report = _report()
    r = make_client(stub_services).post(
        "/api/v1/documents",
        data=_form_fields(),
        files={"file": ("test.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["kind"] == "ingest"
    assert body["status"] == "queued"  # response is built before the task runs
    assert body["result"] is None


def test_upload_document_job_completes_and_is_pollable(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    stub_services.ingestion.report = _report()
    c = make_client(stub_services)
    job_id = c.post(
        "/api/v1/documents",
        data=_form_fields(),
        files={"file": ("test.pdf", _pdf_bytes(), "application/pdf")},
    ).json()["id"]
    body = c.get(f"/api/v1/jobs/{job_id}").json()
    assert body["status"] == "done"
    assert body["result"]["chunks_created"] == 42
    assert body["result"]["sections_found"] == 10


def test_upload_document_passes_metadata_through(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    stub_services.ingestion.report = _report(slug="far-25", sections_found=1, chunks_created=1)
    make_client(stub_services).post(
        "/api/v1/documents",
        data=_form_fields(
            slug="far-25",
            title="Airworthiness Standards",
            version="2024",
            source_url="https://example.gov/far25.pdf",
        ),
        files={"file": ("far25.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert len(stub_services.ingestion.calls) == 1
    pdf_path, meta = stub_services.ingestion.calls[0]
    assert isinstance(pdf_path, Path)
    assert meta.slug == "far-25"
    assert meta.title == "Airworthiness Standards"
    assert meta.version == "2024"
    # The temp upload is cleaned up after ingestion, success or failure.
    assert not pdf_path.exists()


def test_upload_document_ingestion_failure_marks_job_error(make_client, stub_services) -> None:  # type: ignore[no-untyped-def]
    stub_services.ingestion.error = ValueError("corrupt PDF: no text layer")
    c = make_client(stub_services)
    job_id = c.post(
        "/api/v1/documents",
        data=_form_fields(),
        files={"file": ("bad.pdf", _pdf_bytes(), "application/pdf")},
    ).json()["id"]
    body = c.get(f"/api/v1/jobs/{job_id}").json()
    assert body["status"] == "error"
    assert "corrupt PDF" in body["detail"]


def test_upload_document_missing_required_field_422(client: TestClient) -> None:
    fields = _form_fields()
    del fields["license_note"]
    r = client.post(
        "/api/v1/documents",
        data=fields,
        files={"file": ("test.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert r.status_code == 422
