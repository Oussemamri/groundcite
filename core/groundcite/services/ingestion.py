"""IngestionService — parse → structure → chunk → embed → store (spec §6).

Implements spec §6 ``IngestionService.ingest(pdf_path, doc_meta)``. Not yet
implemented (Week 1). Depends on the DocumentParser, Chunker, EmbeddingProvider
and Repository ports; wired by ``container.build_services``.
"""

from __future__ import annotations


class IngestionService:
    """Ingest a text-layer PDF into the clause-aware hierarchy (spec §6)."""
