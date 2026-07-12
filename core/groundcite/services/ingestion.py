"""IngestionService — parse → structure → chunk → embed → store (spec §6).

Orchestrates the DocumentParser, StructureDetector, Chunker, EmbeddingProvider,
TokenCounter and Repository ports (wired in container.py). Idempotent: re-
ingesting a slug upserts the documents row (preserving its id on conflict) and
replaces sections/chunks in ONE transaction (spec §6).

Emits an IngestionReport (spec §6 step 5): sections found, chunks created, a
token histogram, and the orphan-text percentage (<10% is the Week-1 DoD).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from uuid import UUID, uuid4

from groundcite.domain.entities import Chunk, Document, DocumentMeta, ParsedDocument, Section
from groundcite.domain.results import IngestionReport
from groundcite.ports.protocols import (
    Chunker,
    DocumentParser,
    EmbeddingProvider,
    Repository,
    StructureDetector,
    TokenCounter,
)

_PURE_PAGE_NUM_RE = re.compile(r"^\d{1,4}$")

# Token-count histogram buckets (spec §6 step 5).
_HISTO_BUCKETS = [
    (128, "0-128"),
    (256, "129-256"),
    (384, "257-384"),
    (512, "385-512"),
    (10_000, "513+"),
]


class IngestionService:
    """Ingest a text-layer PDF into the clause-aware hierarchy (spec §6)."""

    def __init__(
        self,
        parser: DocumentParser,
        detector: StructureDetector,
        chunker: Chunker,
        embedder: EmbeddingProvider,
        token_counter: TokenCounter,
        repository: Repository,
    ) -> None:
        self._parser = parser
        self._detector = detector
        self._chunker = chunker
        self._embedder = embedder
        self._token_counter = token_counter
        self._repository = repository

    def ingest(self, pdf_path: Path, doc_meta: DocumentMeta) -> IngestionReport:
        # 1. Parse (spec §6 step 1).
        parsed = self._parser.parse(pdf_path)

        # 2. Upsert the Document; the store returns the canonical id (preserved
        #    on slug conflict), which sections/chunks reference.
        document = Document(
            id=uuid4(),
            slug=doc_meta.slug,
            standard_code=doc_meta.standard_code,
            title=doc_meta.title,
            organization=doc_meta.organization,
            version=doc_meta.version,
            language=doc_meta.language,
            source_url=doc_meta.source_url,
            license_note=doc_meta.license_note,
        )
        persisted = self._repository.upsert_document(document)

        # 3. Enrich the parsed document with the store-assigned id and the
        #    standard_code/title the chunker needs for breadcrumbs.
        parsed = parsed.model_copy(
            update={
                "document_id": persisted.id,
                "standard_code": persisted.standard_code,
                "title": persisted.title,
            }
        )

        # 4. Structure detection (spec §6 step 2) — fails loudly if <90%
        #    of text attaches to sections.
        sections, section_text = self._detector.detect(parsed)

        # 5. Chunk (spec §6 step 3) with the injected token counter.
        count_tokens: Callable[[str], int] = self._token_counter.count
        chunks = self._chunker.chunk(parsed, sections, section_text, count_tokens)

        # 6. Embed in batches (spec §6 step 4); chunk content includes the
        #    breadcrumb header, so we embed exactly what is stored.
        if chunks:
            vectors = self._embedder.embed([c.content for c in chunks])
            chunks = [c.model_copy(update={"embedding": vectors[i]}) for i, c in enumerate(chunks)]

        # 7. Replace sections+chunks in one transaction (spec §6 idempotency).
        self._repository.replace_sections_and_chunks(persisted.id, sections, chunks)

        # 8. Report (spec §6 step 5).
        return self._report(parsed, doc_meta, persisted.id, sections, section_text, chunks)

    @staticmethod
    def _report(
        parsed: ParsedDocument,
        doc_meta: DocumentMeta,
        document_id: UUID,
        sections: list[Section],
        section_text: Mapping[UUID, str],
        chunks: Sequence[Chunk],
    ) -> IngestionReport:
        total_chars = sum(
            len(b.text)
            for page in parsed.pages
            for b in page.blocks
            if b.text and not _PURE_PAGE_NUM_RE.match(b.text)
        )
        # Attached text = everything the detector attached to a section (header
        # lines + body), counted WITHOUT the "\n" separators the detector joins
        # blocks with, so it compares apples-to-apples with total_chars (block
        # text lengths). The detector already RAISED if this / total (excluding
        # recognized page-number/running-header noise) fell below 90%.
        attached_chars = sum(len(v.replace("\n", "")) for v in section_text.values())
        orphan_pct = 0.0 if total_chars == 0 else 1.0 - attached_chars / total_chars
        attached_pct = 0.0 if total_chars == 0 else min(1.0, attached_chars / total_chars)

        histogram: dict[str, int] = {label: 0 for _, label in _HISTO_BUCKETS}
        for c in chunks:
            for upper, label in _HISTO_BUCKETS:
                if c.token_count <= upper:
                    histogram[label] += 1
                    break

        return IngestionReport(
            slug=doc_meta.slug,
            standard_code=doc_meta.standard_code,
            sections_found=len(sections),
            chunks_created=len(chunks),
            token_histogram=histogram,
            orphan_pct=orphan_pct,
            attached_pct=attached_pct,
            total_text_chars=total_chars,
            document_id=document_id,
        )
