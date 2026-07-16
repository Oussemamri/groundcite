"""Domain result types & enums for the ask/eval pipelines (spec §7, §8).

Types only, no behaviour. The ``AskEventType`` / ``Stage`` enums are the single
source of truth for the SSE contract (spec §7) that both ``apps/api`` and
``apps/web`` must mirror exactly.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _Frozen(BaseModel):
    """Base for immutable result models."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class AskStatus(StrEnum):
    """Terminal status of an Ask (spec §5 asks.status)."""

    GROUNDED = "grounded"
    ABSTAINED = "abstained"
    ERROR = "error"


class AbstentionReason(StrEnum):
    """Why the grounding gate refused to answer (spec §7 gates A/B)."""

    WEAK_RETRIEVAL = "weak_retrieval"  # Gate A: top score < tau_retrieval
    UNCITED = "uncited"  # Gate B: missing/invalid citations after repair retry


class Stage(StrEnum):
    """Pipeline stage reported over SSE ``stage`` events (spec §7)."""

    RETRIEVING = "retrieving"
    RERANKING = "reranking"
    GENERATING = "generating"


class AskEventType(StrEnum):
    """SSE event types shared by API and web (spec §7). Do not diverge."""

    STAGE = "stage"
    TOKEN = "token"
    CITATIONS = "citations"
    FINAL = "final"
    ERROR = "error"


class Citation(_Frozen):
    """Link from an answer claim to a Chunk (spec §5 citations, §7 contract).

    Never called a reference or source.
    """

    chunk_id: UUID
    rank: int
    score: float
    claim: str | None = None
    clause_path: str | None = None


class RetrievedChunk(_Frozen):
    """A candidate Chunk with its retrieval score, used for ranked passage lists
    (fusion output, reranker output, and abstention ``top_passages``, spec §7).
    """

    chunk_id: UUID
    clause_path: str
    content: str
    score: float


class RetrievalResult(_Frozen):
    """Output of the retrieval half of the ask pipeline (spec §7 steps 0-3).

    Deliberately generation-free: this is what ``AskService.retrieve`` returns,
    and it is the ONLY thing the retrieval-only eval metrics (recall@k, MRR —
    spec §8, §15.1) need. Keeping it a first-class result is what lets the eval
    harness score retrieval without an LLM or a judge.

    ``chunks`` is the final ranked context (top ``context_k``); ``candidates`` is
    the wider fused list kept for abstention ``top_passages`` and debugging.
    ``pipeline_debug`` carries per-stage timings and candidate scores (spec §12).
    """

    question: str
    chunks: tuple[RetrievedChunk, ...]
    candidates: tuple[RetrievedChunk, ...] = ()
    clause_ids: tuple[str, ...] = ()
    reranked: bool = False
    pipeline_debug: dict[str, object] = Field(default_factory=dict)


class Answer(_Frozen):
    """A grounded answer produced by the generator (spec §7 generation contract)."""

    answer_md: str
    citations: tuple[Citation, ...]
    insufficient: bool = False
    confidence: float | None = None


class TokenUsage(_Frozen):
    """Per-call token accounting from the generator (spec §12, AD-1).

    The OpenAI-compatible adapter returns this as the generator's ``StopIteration``
    value so the streaming token loop and the usage accounting come from ONE call;
    it feeds ``pipeline_debug`` (prompt/completion token counts) and ``cost_usd``
    (when the active model has a price entry in config ``model_prices``).
    """

    prompt_tokens: int
    completion_tokens: int


class Abstention(_Frozen):
    """First-class "cannot answer" result; still useful — carries best passages
    for the UI to render (spec §7 abstention payload). Never called a refusal.
    """

    reason: AbstentionReason
    confidence: float | None = None
    top_passages: tuple[RetrievedChunk, ...] = ()


class AskEvent(_Frozen):
    """One event on the SSE stream (spec §7). ``data`` shape depends on ``type``."""

    type: AskEventType
    data: dict[str, object] = Field(default_factory=dict)


class EvalRun(_Frozen):
    """A single execution of an eval Suite (spec §5 eval_runs, §8).

    ``started_at`` and ``suite`` are both optional reads (Week 5 AD-2): the
    write path (``EvalService.run_full``/``run_retrieval``) never sets them —
    ``eval_runs.started_at`` defaults to ``now()`` at insert and ``suite`` is
    derived by joining the run's Cases (all Cases in one run share a suite),
    not a real column. Both surface on the read paths (``get_eval_run``,
    ``list_eval_runs``) for the `/evals` runs table (recency + suite label).
    """

    id: UUID
    git_sha: str
    config: dict[str, object] = Field(default_factory=dict)
    started_at: datetime | None = None
    suite: str | None = None


class EvalResult(_Frozen):
    """Per-Case metrics for one EvalRun (spec §5 eval_results, §8)."""

    run_id: UUID
    case_id: UUID
    recall_at_5: float | None = None
    recall_at_10: float | None = None
    mrr: float | None = None
    citation_precision: float | None = None
    faithfulness: float | None = None
    abstained: bool | None = None
    passed: bool = False
    debug: dict[str, object] = Field(default_factory=dict)


class RetrievalCaseResult(_Frozen):
    """Per-Case retrieval score (spec §8 "we need per-case debug detail").

    ``must_abstain`` cases carry no expected clauses, so recall/MRR are not
    meaningful for them and they are excluded from the suite means. Their
    ``top_score`` is still recorded: the gap between the best score a
    must-abstain case reaches and the worst score a grounded case reaches is
    exactly the evidence needed to set τ_retrieval for Gate A (Week 3).
    """

    case_id: UUID
    question: str
    language: str
    must_abstain: bool
    expected_clauses: tuple[str, ...]
    retrieved_clauses: tuple[str, ...]
    recall_at_5: float
    recall_at_10: float
    reciprocal_rank: float
    first_hit_rank: int | None = None
    top_score: float | None = None


class RetrievalEvalReport(_Frozen):
    """Suite-level retrieval baseline (spec §8, §15.1 — no judge, no LLM).

    Means are taken over SCORABLE cases only (those with expected clauses);
    ``must_abstain_cases`` is reported separately.
    """

    suite: str
    git_sha: str
    reranked: bool
    scored_cases: int
    must_abstain_cases: int
    recall_at_5: float
    recall_at_10: float
    mrr: float
    cases: tuple[RetrievalCaseResult, ...] = ()
    config: dict[str, object] = Field(default_factory=dict)


class FullEvalCaseResult(_Frozen):
    """Per-Case result of a FULL-pipeline eval run (spec §8; Phase 5).

    Distinct from ``RetrievalCaseResult`` (spec §15.1, recall@k/MRR, no LLM):
    this runs the actual answerer through Gates A/B, so it scores what those
    gates DECIDED (citation_precision, abstention_is_correct) rather than what
    was merely retrieved.

    ``top_score`` is the NORMALIZED reranker score Gate A actually compared
    against τ_retrieval (``Answer.confidence`` when GROUNDED,
    ``Abstention.confidence`` when ABSTAINED) — recorded so a τ sweep (Phase 6)
    can be computed from an already-run suite's stored results, never by
    re-asking every case at each candidate τ.
    """

    case_id: UUID
    question: str
    language: str
    must_abstain: bool
    status: AskStatus
    abstention_reason: AbstentionReason | None = None
    abstention_correct: bool
    citation_precision: float | None = None
    faithfulness: float | None = None
    cited_clauses: tuple[str, ...] = ()
    latency_ms: int | None = None
    ask_id: UUID | None = None
    top_score: float | None = None
    # The ERROR event's data["message"] (AD-2's terminal-event contract) — never
    # dropped. Without this an "error" row in the report is a dead end: no DB
    # query and no re-run can recover WHY it failed after the fact.
    error_message: str | None = None


class FullEvalReport(_Frozen):
    """Suite-level full-pipeline baseline (spec §8; Phase 5/6).

    ``mean_citation_precision`` is taken over GROUNDED cases that actually
    carry citations (Gate B guarantees >=1, so this excludes only the
    pathological/error cases, never silently drops a real answer).
    ``abstention_accuracy`` is taken over ALL cases (spec §8: "abstention
    correctness for negative cases" generalizes to every case having a
    correct/incorrect grounded-vs-abstained label).
    """

    suite: str
    git_sha: str
    judge: bool
    total_cases: int
    grounded_cases: int
    abstained_cases: int
    error_cases: int
    abstention_accuracy: float
    mean_citation_precision: float
    mean_faithfulness: float | None = None
    cases: tuple[FullEvalCaseResult, ...] = ()
    config: dict[str, object] = Field(default_factory=dict)


class IngestionReport(_Frozen):
    """Result of one IngestionService.ingest run (spec §6 step 5).

    Carries the sections-found / chunks-created counts, a coarse token-count
    histogram (bucket -> number of chunks), the orphan-text percentage, and the
    attached ratio that gates ingestion (≥90%, spec §6 step 2). The CLI prints
    this; the DoD is <10% orphan on the fetched FAR Part 25.
    """

    slug: str
    standard_code: str
    sections_found: int
    chunks_created: int
    token_histogram: dict[str, int] = Field(default_factory=dict)
    orphan_pct: float
    attached_pct: float
    total_text_chars: int
    document_id: UUID
