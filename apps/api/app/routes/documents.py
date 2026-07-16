"""Read routes: documents + chunks (spec §9, §10; AD-4 reads).

- ``GET /api/v1/documents`` — list Documents.
- ``GET /api/v1/documents/{slug}`` — one Document + its section tree (clause
  tree); ``?include=chunks`` also returns the ordered chunk list for the
  reader page.
- ``GET /api/v1/chunks/{id}`` — citation resolution target (one chunk).

Routes are thin (parse → service → serialize). 404s for unknown slug/id raise
``NotFoundError`` → RFC-7807 problem+json (AD-6).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from app.deps import get_services
from app.errors import NotFoundError, not_found_or_raise
from app.models import ChunkOut, DocumentOut, SectionOut
from groundcite.container import Services

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
