"""API response models (spec §9, AD-6).

Pydantic models mapped EXPLICITLY from domain objects — never ``model_dump()``
a domain entity into a response (spec §9). Domain types come from
``groundcite.domain``; this module imports only domain + stdlib, never services
or adapters (spec §4 dependency rule). Field names use the spec §2.1 ubiquitous
language (Ask, Citation, Document, Section, Chunk, Suite/Case/Run).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.jobs import Job
from groundcite.domain.entities import Ask, Chunk, Conversation, Document, EvalCase, Section
from groundcite.domain.results import Citation, EvalResult, EvalRun


class _Out(BaseModel):
    """Base for API response models (extra-forbid, like the domain models)."""

    model_config = ConfigDict(extra="forbid")


class DocumentOut(_Out):
    slug: str
    standard_code: str
    title: str
    organization: str
    version: str | None = None
    language: str
    source_url: str | None = None
    license_note: str
    ingested_at: datetime | None = None

    @classmethod
    def from_domain(cls, d: Document) -> DocumentOut:
        return cls(
            slug=d.slug,
            standard_code=d.standard_code,
            title=d.title,
            organization=d.organization,
            version=d.version,
            language=d.language,
            source_url=d.source_url,
            license_note=d.license_note,
            ingested_at=d.ingested_at,
        )


class SectionOut(_Out):
    id: UUID
    parent_id: UUID | None = None
    clause_id: str
    title: str | None = None
    level: int
    ordinal: int

    @classmethod
    def from_domain(cls, s: Section) -> SectionOut:
        return cls(
            id=s.id,
            parent_id=s.parent_id,
            clause_id=s.clause_id,
            title=s.title,
            level=s.level,
            ordinal=s.ordinal,
        )


class ChunkOut(_Out):
    id: UUID
    document_id: UUID
    section_id: UUID
    clause_path: str
    content: str
    token_count: int
    page_start: int | None = None
    page_end: int | None = None

    @classmethod
    def from_domain(cls, c: Chunk) -> ChunkOut:
        # Embedding is intentionally not serialized — it is 1024 floats of no UI
        # interest and would bloat the reader payload.
        return cls(
            id=c.id,
            document_id=c.document_id,
            section_id=c.section_id,
            clause_path=c.clause_path,
            content=c.content,
            token_count=c.token_count,
            page_start=c.page_start,
            page_end=c.page_end,
        )


class CitationOut(_Out):
    chunk_id: UUID
    rank: int
    score: float
    claim: str | None = None
    clause_path: str | None = None

    @classmethod
    def from_domain(cls, c: Citation) -> CitationOut:
        return cls(
            chunk_id=c.chunk_id,
            rank=c.rank,
            score=c.score,
            claim=c.claim,
            clause_path=c.clause_path,
        )


class AskOut(_Out):
    id: UUID
    question: str
    status: str
    answer_md: str | None = None
    confidence: float | None = None
    latency_ms: int | None = None
    cost_usd: Decimal | None = None
    pipeline_debug: dict[str, object]
    created_at: datetime | None = None
    citations: list[CitationOut]

    @classmethod
    def from_domain(cls, ask: Ask, citations: list[Citation]) -> AskOut:
        return cls(
            id=ask.id,
            question=ask.question,
            status=ask.status.value,
            answer_md=ask.answer_md,
            confidence=ask.confidence,
            latency_ms=ask.latency_ms,
            cost_usd=ask.cost_usd,
            pipeline_debug=ask.pipeline_debug,
            created_at=ask.created_at,
            citations=[CitationOut.from_domain(c) for c in citations],
        )


class ConversationOut(_Out):
    """A conversation summary (Week 6, spec §9 GET /conversations). Groups
    already-independent Asks -- turn_count/latest_status are read-only,
    derived at read time (never re-computed generation state)."""

    id: UUID
    title: str
    created_at: datetime | None = None
    turn_count: int | None = None
    latest_status: str | None = None

    @classmethod
    def from_domain(cls, c: Conversation) -> ConversationOut:
        return cls(
            id=c.id,
            title=c.title,
            created_at=c.created_at,
            turn_count=c.turn_count,
            latest_status=c.latest_status.value if c.latest_status is not None else None,
        )


class ConversationDetailOut(_Out):
    """One conversation's full turn history (spec §9 GET /conversations/{id})
    -- each turn the same shape GET /asks/{id} already returns."""

    conversation: ConversationOut
    asks: list[AskOut]


class EvalRunOut(_Out):
    id: UUID
    git_sha: str
    config: dict[str, object]
    started_at: datetime | None = None
    suite: str | None = None

    @classmethod
    def from_domain(cls, r: EvalRun) -> EvalRunOut:
        return cls(
            id=r.id,
            git_sha=r.git_sha,
            config=r.config,
            started_at=r.started_at,
            suite=r.suite,
        )


class EvalResultOut(_Out):
    run_id: UUID
    case_id: UUID
    # Case metadata (Week 5 AD-2) -- not on EvalResult itself; joined from
    # eval_cases via EvalService.get_cases. None when the case id is unknown
    # (should not happen for a real run, but never silently fabricated).
    question: str | None = None
    expected_clauses: list[str] = Field(default_factory=list)
    must_abstain: bool | None = None
    language: str | None = None
    recall_at_5: float | None = None
    recall_at_10: float | None = None
    mrr: float | None = None
    citation_precision: float | None = None
    faithfulness: float | None = None
    abstained: bool | None = None
    passed: bool
    debug: dict[str, object]

    @classmethod
    def from_domain(cls, r: EvalResult, case: EvalCase | None = None) -> EvalResultOut:
        return cls(
            run_id=r.run_id,
            case_id=r.case_id,
            question=case.question if case is not None else None,
            expected_clauses=list(case.expected_clauses) if case is not None else [],
            must_abstain=case.must_abstain if case is not None else None,
            language=case.language if case is not None else None,
            recall_at_5=r.recall_at_5,
            recall_at_10=r.recall_at_10,
            mrr=r.mrr,
            citation_precision=r.citation_precision,
            faithfulness=r.faithfulness,
            abstained=r.abstained,
            passed=r.passed,
            debug=r.debug,
        )


class EvalRunAggregatesOut(_Out):
    """Per-run headline metrics (Week 5 AD-2/AD-4), computed HERE from the
    already-persisted per-case rows -- never by re-running (rule 4). Mirrors
    ``FullEvalReport``'s own definitions (``services/eval.py`` run_full, NOT
    touched this week): abstention_accuracy = mean(passed), mean_citation_precision
    over cases that carry one, recall/MRR means over cases with a value."""

    scored_cases: int
    mean_recall_at_5: float | None = None
    mean_recall_at_10: float | None = None
    mean_mrr: float | None = None
    mean_citation_precision: float | None = None
    abstention_accuracy: float | None = None

    @classmethod
    def from_results(cls, results: list[EvalResult]) -> EvalRunAggregatesOut:
        def _mean(vals: list[float]) -> float | None:
            return sum(vals) / len(vals) if vals else None

        return cls(
            scored_cases=len(results),
            mean_recall_at_5=_mean([r.recall_at_5 for r in results if r.recall_at_5 is not None]),
            mean_recall_at_10=_mean(
                [r.recall_at_10 for r in results if r.recall_at_10 is not None]
            ),
            mean_mrr=_mean([r.mrr for r in results if r.mrr is not None]),
            mean_citation_precision=_mean(
                [r.citation_precision for r in results if r.citation_precision is not None]
            ),
            abstention_accuracy=_mean([1.0 if r.passed else 0.0 for r in results]),
        )


class EvalRunDetailOut(_Out):
    run: EvalRunOut
    results: list[EvalResultOut]
    aggregates: EvalRunAggregatesOut


class JobOut(_Out):
    """A background write's status (spec §9; AD-5). ``result``'s shape depends
    on ``kind`` -- an ingest job's is an ingestion report summary, an
    eval_run job's is ``{"run_id": ...}``."""

    id: UUID
    kind: str
    status: str
    detail: str | None = None
    result: dict[str, object] | None = None
    created_at: datetime

    @classmethod
    def from_job(cls, job: Job) -> JobOut:
        return cls(
            id=job.id,
            kind=job.kind.value,
            status=job.status.value,
            detail=job.detail,
            result=job.result,
            created_at=job.created_at,
        )
