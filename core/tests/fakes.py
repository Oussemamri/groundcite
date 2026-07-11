"""Fake ports for unit tests (spec §17 rule 3: no network, no DB, no models).

Deterministic, no third-party deps. Used by service-layer tests so the suite
runs without the pdf/embed extras or a live Postgres.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from groundcite.domain.entities import Ask, Chunk, Document, EvalCase, Section
from groundcite.domain.results import EvalRun
from groundcite.ports.protocols import Vector

# A dense embedding vector the chunk store will actually use (1024-d), so fake
# embeddings exercise the same shape as the real bge-m3 adapter.
_FAKE_DIM = 1024


class FakeEmbedder:
    """Returns deterministic 1024-d zero vectors (no model load)."""

    def __init__(self, dimension: int = _FAKE_DIM) -> None:
        self._dim = dimension

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        zero = tuple(0.0 for _ in range(self._dim))
        return [zero for _ in texts]


class FakeTokenCounter:
    """Whitespace token counter — deterministic, no tokenizer library."""

    def count(self, text: str) -> int:
        return len(text.split())


class FakeRepository:
    """In-memory Repository for IngestionService unit tests.

    ``replace_sections_and_chunks`` replaces in one logical transaction (spec §6
    idempotency): rows for a document are overwritten so re-ingesting a slug
    leaves counts unchanged.
    """

    def __init__(self) -> None:
        self.documents: dict[str, Document] = {}
        self.sections: dict[str, list[Section]] = {}
        self.chunks: dict[str, list[Chunk]] = {}
        self.asks: dict[UUID, Ask] = {}
        self.eval_runs: dict[UUID, EvalRun] = {}
        self.replace_calls: int = 0

    def upsert_document(self, document: Document) -> Document:
        existing = self.documents.get(document.slug)
        if existing:
            # Preserve the canonical id on slug conflict (mirrors the pg_repo
            # ON CONFLICT … RETURNING id), so re-ingest keeps the same id.
            kept = existing.model_copy(
                update={
                    "standard_code": document.standard_code,
                    "title": document.title,
                    "organization": document.organization,
                    "version": document.version,
                    "language": document.language,
                    "source_url": document.source_url,
                    "license_note": document.license_note,
                }
            )
            self.documents[document.slug] = kept
            return kept
        self.documents[document.slug] = document
        return document

    def get_document(self, slug: str) -> Document | None:
        return self.documents.get(slug)

    def list_documents(self) -> list[Document]:
        return list(self.documents.values())

    def replace_sections_and_chunks(
        self, document_id: UUID, sections: Sequence[Section], chunks: Sequence[Chunk]
    ) -> None:
        self.replace_calls += 1
        slug = next((s for s, d in self.documents.items() if d.id == document_id), None)
        if slug is None:
            raise KeyError(f"no document for id {document_id}")
        self.sections[slug] = list(sections)
        self.chunks[slug] = list(chunks)

    def get_section_tree(self, document_id: UUID) -> list[Section]:
        slug = next((s for s, d in self.documents.items() if d.id == document_id), None)
        return list(self.sections.get(slug, ())) if slug else []

    def get_chunk(self, chunk_id: UUID) -> Chunk | None:
        for clist in self.chunks.values():
            for c in clist:
                if c.id == chunk_id:
                    return c
        return None

    def save_ask(self, ask: Ask) -> None:
        self.asks[ask.id] = ask

    def get_ask(self, ask_id: UUID) -> Ask | None:
        return self.asks.get(ask_id)

    def load_suite(self, suite: str) -> list[EvalCase]:
        return []

    def save_eval_run(self, run: EvalRun) -> None:
        self.eval_runs[run.id] = run
