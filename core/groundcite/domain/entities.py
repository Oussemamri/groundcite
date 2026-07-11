"""Domain entities — the persistent nouns of GroundCite (spec §2.1, §5).

Types only, no behaviour. Every model is a frozen pydantic v2 model so domain
objects are immutable and hashable. Field names track the Postgres schema in
spec §5 verbatim; the ubiquitous language in spec §2.1 is used everywhere and
synonyms (file/pdf, heading, passage, query, ...) are never introduced.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from groundcite.domain.results import AskStatus


class _Frozen(BaseModel):
    """Base for immutable domain models."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Document(_Frozen):
    """One standard, e.g. "14 CFR Part 25" or "ECSS-E-ST-40C" (spec §5 documents).

    Never called a file, pdf, or source.
    """

    id: UUID
    slug: str
    standard_code: str
    title: str
    organization: str
    version: str | None = None
    language: str = "en"
    source_url: str | None = None
    license_note: str
    ingested_at: datetime | None = None


class Section(_Frozen):
    """A node in a document's clause hierarchy, e.g. "5.4.2" (spec §5 sections).

    Never called a heading or chapter.
    """

    id: UUID
    document_id: UUID
    parent_id: UUID | None = None
    clause_id: str
    title: str | None = None
    level: int
    ordinal: int


class Chunk(_Frozen):
    """A retrievable text unit tied to a Section (spec §5 chunks, §6 chunking).

    ``content`` includes the breadcrumb header prepended at ingestion (spec §6).
    Never called a passage, snippet, or fragment.
    """

    id: UUID
    document_id: UUID
    section_id: UUID
    clause_path: str
    content: str
    token_count: int
    page_start: int | None = None
    page_end: int | None = None
    embedding: tuple[float, ...] | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class Ask(_Frozen):
    """A user question resolved through one pipeline run (spec §5 asks, §7).

    Never called a query (reserved for DB), chat, or prompt.
    """

    id: UUID
    question: str
    status: AskStatus
    answer_md: str | None = None
    confidence: float | None = None
    latency_ms: int | None = None
    cost_usd: Decimal | None = None
    pipeline_debug: dict[str, object] = Field(default_factory=dict)
    created_at: datetime | None = None


class EvalCase(_Frozen):
    """One golden case in an eval Suite (spec §5 eval_cases, §8).

    Eval terminology is Suite / Case / Run — never "test" (reserved for pytest).
    """

    id: UUID
    suite: str
    question: str
    expected_clauses: tuple[str, ...]
    expected_facts: tuple[str, ...] = ()
    must_abstain: bool = False
    language: str = "en"


class ParsedPage(_Frozen):
    """Raw output of the DocumentParser port: one PDF page's text-layer content
    plus the layout signals structure detection needs (spec §6 step 1).
    """

    page_number: int
    text: str
    max_font_size: float | None = None
    has_bold: bool = False
