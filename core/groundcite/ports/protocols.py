"""Port Protocols (spec §4).

Structural interfaces the services depend on. Adapters (spec §4 adapters/)
implement these; ``container.build_services`` wires concrete adapters from
config. Types only — no bodies, no ``Any`` (spec §17 rule 5).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable
from uuid import UUID

from groundcite.domain.entities import (
    Ask,
    Chunk,
    Document,
    EvalCase,
    ParsedDocument,
    Section,
)
from groundcite.domain.results import EvalRun

# A dense embedding vector. Dimension is fixed at 1024 (bge-m3) and locked —
# changing it means a full re-embed (spec §5, §11, prep task P4).
type Vector = tuple[float, ...]

# Raw text span per Section, keyed by Section.id (spec §6 type seam). Kept out
# of the Section domain entity (Section stays a pure tree node matching the
# ``sections`` table 1:1) — the parallel-text-map seam between structure
# detection and chunking.
type SectionTextMap = Mapping[UUID, str]


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Turns text into dense vectors, batched (spec §6 step 4, §11 bge-m3)."""

    @property
    def dimension(self) -> int: ...

    def embed(self, texts: Sequence[str]) -> list[Vector]: ...


@runtime_checkable
class LLMProvider(Protocol):
    """Streaming text generator for the answerer (spec §7 step 5, §11)."""

    def stream(self, system: str, user: str) -> Iterator[str]: ...


@runtime_checkable
class Reranker(Protocol):
    """Cross-encoder that reorders fused candidates (spec §7 step 3, §11)."""

    def rerank(
        self, question: str, candidates: Sequence[Chunk], top_k: int
    ) -> list[tuple[Chunk, float]]: ...


@runtime_checkable
class VectorIndex(Protocol):
    """Dense nearest-neighbour search over chunk embeddings (spec §7 step 1a)."""

    def search(
        self,
        embedding: Vector,
        top_k: int,
        document_slugs: Sequence[str] | None = None,
    ) -> list[tuple[Chunk, float]]: ...


@runtime_checkable
class LexicalIndex(Protocol):
    """Full-text search + exact clause-path fast path (spec §7 steps 1b, 1c)."""

    def search(
        self,
        query: str,
        top_k: int,
        document_slugs: Sequence[str] | None = None,
    ) -> list[tuple[Chunk, float]]: ...

    def match_clause(
        self, clause_path: str, document_slugs: Sequence[str] | None = None
    ) -> list[Chunk]: ...


@runtime_checkable
class DocumentParser(Protocol):
    """Extracts text + layout signals from a text-layer PDF (spec §6 step 1).

    Output is a single ``ParsedDocument`` whose ``pages`` carry ordered text
    blocks with font-size/bold signals. Both the PyMuPDF (lite/CI) and Docling
    (default) adapters share this shape and one contract test (spec §6 step 1).
    """

    def parse(self, pdf_path: Path) -> ParsedDocument: ...


@runtime_checkable
class StructureDetector(Protocol):
    """Builds the Section clause tree from a parsed document (spec §6 step 2).

    NOT a private step inside the parser and NOT inlined in the chunker (spec §6
    binding): it must be fake-testable per CLAUDE rule 3 without a real PDF, and
    organization-specific numbering (FAA/EASA CFR-style ``§ 25.1309``,
    ``(a)(1)(i)`` vs. ECSS/NASA numeric hierarchy) must be swappable per
    ``documents.organization``. Returns the Section tree for persistence PLUS a
    parallel ``SectionTextMap`` giving the chunker raw text per section.
    """

    def detect(self, doc: ParsedDocument) -> tuple[list[Section], SectionTextMap]: ...


@runtime_checkable
class Chunker(Protocol):
    """Clause-aware chunking with breadcrumb headers (spec §6 step 3).

    Signature is binding (spec §6 type seam / §6.1 #1): the chunker consumes the
    parsed document, the Section tree, the parallel section-text map, and an
    injected ``count_tokens`` callable. It NEVER imports an embedding library
    directly — token counting is injected so swapping the embedding provider
    swaps the token counter in lockstep, wired once in ``container.py``.
    """

    def chunk(
        self,
        doc: ParsedDocument,
        sections: Sequence[Section],
        section_text: SectionTextMap,
        count_tokens: Callable[[str], int],
    ) -> list[Chunk]: ...


@runtime_checkable
class TokenCounter(Protocol):
    """Counts tokens with the configured embedder's tokenizer (spec §6 §6.1 #4).

    Uses the target embedder's own tokenizer as the token-count source of truth
    so chunk size limits stay accurate for whichever embedder is active. Wired by
    ``container.py`` and injected into the Chunker as ``count_tokens``.
    """

    def count(self, text: str) -> int: ...


@runtime_checkable
class Repository(Protocol):
    """Persistence port over the Postgres schema (spec §5). Adapter: pg_repo."""

    # --- documents / sections / chunks ---
    def upsert_document(self, document: Document) -> Document: ...

    def get_document(self, slug: str) -> Document | None: ...

    def list_documents(self) -> list[Document]: ...

    def replace_sections_and_chunks(
        self, document_id: UUID, sections: Sequence[Section], chunks: Sequence[Chunk]
    ) -> None: ...

    def get_section_tree(self, document_id: UUID) -> list[Section]: ...

    def get_chunk(self, chunk_id: UUID) -> Chunk | None: ...

    # --- asks / citations ---
    def save_ask(self, ask: Ask) -> None: ...

    def get_ask(self, ask_id: UUID) -> Ask | None: ...

    # --- evals ---
    def load_suite(self, suite: str) -> list[EvalCase]: ...

    def save_eval_run(self, run: EvalRun) -> None: ...
