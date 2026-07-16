"""Documents + chunks routes (spec §9, §10; AD-4 reads, AD-5 write).

- ``GET /api/v1/documents`` — list Documents.
- ``GET /api/v1/documents/{slug}`` — one Document + its section tree (clause
  tree); ``?include=chunks`` also returns the ordered chunk list for the
  reader page.
- ``GET /api/v1/chunks/{id}`` — citation resolution target (one chunk).
- ``POST /api/v1/documents`` — multipart PDF + metadata -> ``{job_id}``
  (spec §9 verbatim). Ingestion (parse -> chunk -> embed -> persist, ~35 min
  for the full far-25 corpus) runs as a BackgroundTask (AD-5); the upload
  goes to a ``tempfile`` -- never into the repo -- and is removed after the
  job finishes either way.

Routes are thin (parse → service → serialize). 404s for unknown slug/id raise
``NotFoundError`` → RFC-7807 problem+json (AD-6).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, ConfigDict

from app.deps import get_jobs, get_services
from app.errors import NotFoundError, not_found_or_raise
from app.jobs import JobKind, JobRegistry
from app.logging_conf import get_logger
from app.models import ChunkOut, DocumentOut, JobOut, SectionOut
from groundcite.container import Services
from groundcite.domain.entities import DocumentMeta

router = APIRouter(prefix="/api/v1", tags=["library"])


class DocumentDetailOut(BaseModel):
    """Composite for ``GET /documents/{slug}`` — Document + section tree,
    optionally the ordered chunk list (spec §10 reader). Built explicitly, never
    via ``model_dump`` of a domain entity (AD-6)."""

    model_config = ConfigDict(extra="forbid")

    document: DocumentOut
    sections: list[SectionOut]
    chunks: list[ChunkOut] | None = None


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(services: Services = Depends(get_services)) -> list[DocumentOut]:
    return [DocumentOut.from_domain(d) for d in services.library.list_documents()]


@router.get("/documents/{slug}", response_model=DocumentDetailOut)
def get_document(
    slug: str,
    include: list[str] | None = Query(default=None),
    services: Services = Depends(get_services),
) -> DocumentDetailOut:
    doc = services.library.get_document(slug)
    if doc is None:
        raise NotFoundError(slug=slug, label="document")
    sections = services.library.get_section_tree(doc.id)
    chunks = None
    if include and "chunks" in include:
        chunks = [ChunkOut.from_domain(c) for c in services.library.list_chunks(doc.id)]
    return DocumentDetailOut(
        document=DocumentOut.from_domain(doc),
        sections=[SectionOut.from_domain(s) for s in sections],
        chunks=chunks,
    )


@router.get("/chunks/{chunk_id}", response_model=ChunkOut)
def get_chunk(chunk_id: str, services: Services = Depends(get_services)) -> ChunkOut:
    # A malformed id identifies no chunk → 404 (not a 422 validation error).
    try:
        cid = UUID(chunk_id)
    except ValueError as exc:
        raise NotFoundError(slug=chunk_id, label="chunk") from exc
    chunk = not_found_or_raise(services.library.get_chunk(cid), slug=chunk_id, label="chunk")
    return ChunkOut.from_domain(chunk)


def _run_ingest(
    services: Services, jobs: JobRegistry, job_id: UUID, pdf_path: Path, meta: DocumentMeta
) -> None:
    log = get_logger("app.documents.ingest")
    jobs.mark_running(job_id)
    log.info("ingest_started", job_id=str(job_id), slug=meta.slug)
    try:
        report = services.ingestion.ingest(pdf_path, meta)
        jobs.mark_done(
            job_id,
            {
                "slug": report.slug,
                "sections_found": report.sections_found,
                "chunks_created": report.chunks_created,
                "orphan_pct": report.orphan_pct,
                "attached_pct": report.attached_pct,
            },
        )
        log.info("ingest_done", job_id=str(job_id), chunks_created=report.chunks_created)
    except Exception as exc:
        jobs.mark_error(job_id, str(exc))
        log.exception("ingest_failed", job_id=str(job_id), error=str(exc))
    finally:
        os.unlink(pdf_path)  # never leave the upload on disk (spec §13, never in the repo)


@router.post("/documents", response_model=JobOut, status_code=202)
def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    slug: str = Form(...),
    standard_code: str = Form(...),
    title: str = Form(...),
    organization: str = Form(...),
    license_note: str = Form(...),
    version: str | None = Form(default=None),
    language: str = Form(default="en"),
    source_url: str | None = Form(default=None),
    services: Services = Depends(get_services),
    jobs: JobRegistry = Depends(get_jobs),
) -> JobOut:
    fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    with os.fdopen(fd, "wb") as f:
        f.write(file.file.read())
    meta = DocumentMeta(
        slug=slug,
        standard_code=standard_code,
        title=title,
        organization=organization,
        license_note=license_note,
        version=version,
        language=language,
        source_url=source_url,
    )
    job = jobs.create(JobKind.INGEST)
    background_tasks.add_task(_run_ingest, services, jobs, job.id, Path(tmp_path), meta)
    return JobOut.from_job(job)
