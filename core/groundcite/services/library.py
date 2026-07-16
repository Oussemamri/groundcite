"""LibraryService — document library + clause-tree reads (spec §9, §10).

Implements the read side behind ``GET /documents`` / ``GET /documents/{slug}``
and the reader's clause tree (spec §9, §10). Thin: delegates to the Repository
port so the API depends on a service, not on Repository directly (spec §4
dependency rule). The methods are split (document / section_tree / chunks) so
the API controls composition — e.g. ``GET /documents/{slug}`` returns the doc +
section tree and only includes chunks when ``?include=chunks`` is asked.
"""

from __future__ import annotations

from uuid import UUID

from groundcite.domain.entities import Chunk, Document, Section
from groundcite.ports.protocols import Repository


class LibraryService:
    """List Documents and resolve their Section trees + chunk lists (spec §9, §10)."""

    def __init__(self, repository: Repository) -> None:
        self._repository = repository

    def list_documents(self) -> list[Document]:
        return self._repository.list_documents()

    def get_document(self, slug: str) -> Document | None:
        return self._repository.get_document(slug)

    def get_section_tree(self, document_id: UUID) -> list[Section]:
        return self._repository.get_section_tree(document_id)

    def list_chunks(self, document_id: UUID) -> list[Chunk]:
        return self._repository.list_chunks(document_id)
