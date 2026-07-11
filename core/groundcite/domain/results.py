"""Domain result types & enums for the ask/eval pipelines (spec §7, §8).

Types only, no behaviour. The ``AskEventType`` / ``Stage`` enums are the single
source of truth for the SSE contract (spec §7) that both ``apps/api`` and
``apps/web`` must mirror exactly.
"""

from __future__ import annotations

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


class Answer(_Frozen):
    """A grounded answer produced by the generator (spec §7 generation contract)."""

    answer_md: str
    citations: tuple[Citation, ...]
    insufficient: bool = False
    confidence: float | None = None


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
    """A single execution of an eval Suite (spec §5 eval_runs, §8)."""

    id: UUID
    git_sha: str
    config: dict[str, object] = Field(default_factory=dict)


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
