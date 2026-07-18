"""AskService — the retrieval → gate → generate → gate pipeline (spec §7).

Week 2 implemented the retrieval half (``retrieve``), LLM-free, so evals can score
retrieval without a judge or answerer (§8 "most stable CI signal"). Week 3 layers
``ask()`` on top of the SAME ``retrieve`` (AD-2 — no duplication of the retrieval
steps): a generator of ``AskEvent``s.

    STAGE(retrieving) → retrieve() → STAGE(reranking) → Gate A → STAGE(generating)
    → TOKEN* → parse → [repair] → Gate B → CITATIONS → persist → FINAL (or ERROR)

Gate A (AD-3): abstain when the top NORMALIZED RERANKER score < τ_retrieval — so
generation mode REQUIRES the reranker (RRF cannot separate grounded from
must-abstain, §1 evidence). An exact clause-ID match (spec §7 step 1c) bypasses
τ by construction: the user asked for a specific clause we hold.
Gate B (AD-5): every cited chunk_id ∈ the provided context set and ≥1 citation
per answer paragraph; one repair retry, then ABSTAIN(reason=UNCITED).
Mapping (AD-4): ``insufficient: true`` → ABSTAIN(reason=WEAK_RETRIEVAL); a
citation-validity failure → ABSTAIN(reason=UNCITED).

Everything here is orchestration over injected ports — no adapter imports, no
config import (spec §4 dependency rule). Cost uses the injected price map and
the LLM's ``model_name``; an unpriced model → ``cost_usd`` NULL (AD-6).
"""

from __future__ import annotations

import time
from collections.abc import Generator, Iterator, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from groundcite.domain.entities import Ask, Chunk, Conversation
from groundcite.domain.results import (
    Abstention,
    AbstentionReason,
    Answer,
    AskEvent,
    AskEventType,
    AskStatus,
    Citation,
    RetrievalResult,
    RetrievedChunk,
    TokenUsage,
)
from groundcite.ports.protocols import (
    EmbeddingProvider,
    LexicalIndex,
    LLMProvider,
    Repository,
    Reranker,
    VectorIndex,
)
from groundcite.services.answer_parse import ParsedAnswer, ParseError, RawCitation, parse_answer
from groundcite.services.clause_detect import detect_clause_ids
from groundcite.services.fusion import fuse
from groundcite.services.lang_detect import detect_language
from groundcite.services.metrics import matches
from groundcite.services.prompts.answerer import (
    SYSTEM_PROMPT,
    chunk_id_set,
    render_repair,
    render_user,
)

# Per-million-token divisor for cost (prices in USD / 1M tokens).
_PER_MILLION = Decimal("1000000")


class AskService:
    """Resolve one Ask into a grounded Answer or a first-class Abstention (spec §7)."""

    def __init__(
        self,
        embedder: EmbeddingProvider,
        vector_index: VectorIndex,
        lexical_index: LexicalIndex,
        reranker: Reranker | None = None,
        *,
        rrf_k: int = 60,
        candidates_dense: int = 30,
        candidates_lexical: int = 30,
        fused_k: int = 20,
        context_k: int = 6,
        llm: LLMProvider | None = None,
        # Matches config.Settings.tau_retrieval's default — kept in sync
        # deliberately (rule 9 spirit): container.py always passes the config
        # value explicitly, but this fallback exists for direct/test
        # construction, and it must never silently regress to the tau=0.35
        # value Week 3 Phase 6 measured leaking 25% of must-abstain cases
        # (docs/WEEK3_RESULTS.md, spec §7.1).
        tau_retrieval: float = 0.70,
        repository: Repository | None = None,
        model_prices: Mapping[str, tuple[float, float]] | None = None,
    ) -> None:
        self._embedder = embedder
        self._vector = vector_index
        self._lexical = lexical_index
        # None ⇒ the rerank stage is off (RERANKER_ENABLED=false), wired in container.
        self._reranker = reranker
        self._rrf_k = rrf_k
        self._candidates_dense = candidates_dense
        self._candidates_lexical = candidates_lexical
        self._fused_k = fused_k
        self._context_k = context_k
        # Generation half (Week 3). None ⇒ ask() raises (AD-1/AD-3); retrieve() ignores them.
        self._llm = llm
        self._tau_retrieval = tau_retrieval
        self._repository = repository
        self._model_prices = model_prices or {}

    # --- retrieval half (Week 2, unchanged) -----------------------------------

    def retrieve(
        self,
        question: str,
        document_slugs: Sequence[str] | None = None,
        top_k: int | None = None,
    ) -> RetrievalResult:
        """Run retrieval steps 0-3 for ``question`` (spec §7). No LLM involved."""
        context_k = self._context_k if top_k is None else top_k
        timings: dict[str, float] = {}

        # [0] clause-ID detection
        started = time.perf_counter()
        clause_ids = detect_clause_ids(question)
        timings["detect_ms"] = _ms_since(started)

        # [1a] dense
        started = time.perf_counter()
        query_vector = self._embedder.embed([question])[0]
        dense = self._vector.search(query_vector, self._candidates_dense, document_slugs)
        timings["dense_ms"] = _ms_since(started)

        # [1b] lexical
        started = time.perf_counter()
        lexical = self._lexical.search(question, self._candidates_lexical, document_slugs)
        timings["lexical_ms"] = _ms_since(started)

        # [1c] clause fast path — exact hits only, injected at rank 1 by fuse()
        started = time.perf_counter()
        clause_hits: list[Chunk] = []
        for clause_id in clause_ids:
            clause_hits.extend(self._lexical.match_clause(clause_id, document_slugs))
        timings["clause_ms"] = _ms_since(started)

        # [2] RRF fusion
        started = time.perf_counter()
        fused = fuse(dense, lexical, clause_hits, self._rrf_k, self._fused_k)
        timings["fuse_ms"] = _ms_since(started)

        # [3] rerank (optional)
        started = time.perf_counter()
        reranked = False
        if self._reranker is not None and fused:
            ranked = self._reranker.rerank(question, [c for c, _ in fused], context_k)
            reranked = True
        else:
            ranked = fused[:context_k]
        timings["rerank_ms"] = _ms_since(started)

        return RetrievalResult(
            question=question,
            chunks=tuple(_retrieved(c, s) for c, s in ranked),
            candidates=tuple(_retrieved(c, s) for c, s in fused),
            clause_ids=tuple(clause_ids),
            reranked=reranked,
            pipeline_debug={
                "timings_ms": timings,
                "counts": {
                    "dense": len(dense),
                    "lexical": len(lexical),
                    "clause_fast_path": len(clause_hits),
                    "fused": len(fused),
                    "context": len(ranked),
                },
                "document_slugs": list(document_slugs) if document_slugs else [],
            },
        )

    # --- generation half (Week 3) ---------------------------------------------

    def ask(
        self,
        question: str,
        document_slugs: Sequence[str] | None = None,
        conversation_id: UUID | None = None,
    ) -> Iterator[AskEvent]:
        """Full §7 pipeline → a stream of ``AskEvent``s (AD-2). One terminal
        event (FINAL or ERROR) last. Raises a config error at call time if the
        prerequisites for full mode are missing (AD-1/AD-3).

        ``conversation_id`` (Week 6) only TAGS the persisted ``Ask`` row and
        the terminal event's data -- it never changes what gets retrieved or
        generated. No prior-turn context is read or passed to the LLM; each
        call is still one fully independent pipeline run (spec §3.2)."""
        if self._llm is None:
            raise RuntimeError(
                "ask() requires an LLM provider (AD-1); the container did not wire one."
            )
        if self._reranker is None:
            raise RuntimeError(
                "Generation mode requires the normalized reranker score for Gate A "
                "(AD-3): set RERANKER_ENABLED=true. Use `groundcite ask --retrieval-only` "
                "to run retrieval without generating."
            )
        return self._ask_events(question, document_slugs, conversation_id)

    # --- replay reads (Week 4: ``GET /asks/{id}``, spec §9) -------------------
    # Thin Repository delegates so the API owns no adapter reference (§4
    # dependency rule). None when no repository is wired (mirrors the optional
    # repository in container), matching EvalService.get_report's contract.

    def get_ask(self, ask_id: UUID) -> Ask | None:
        if self._repository is None:
            return None
        return self._repository.get_ask(ask_id)

    def get_ask_citations(self, ask_id: UUID) -> list[Citation]:
        if self._repository is None:
            return []
        return self._repository.get_ask_citations(ask_id)

    # --- conversations (Week 6): thin repository delegates, same shape as
    # get_ask/get_ask_citations above -- conversations are "more things
    # AskService reads/writes about Asks," not a separate service. ----------

    def create_conversation(self, title: str) -> Conversation | None:
        if self._repository is None:
            return None
        return self._repository.create_conversation(title)

    def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        if self._repository is None:
            return None
        return self._repository.get_conversation(conversation_id)

    def list_conversations(self) -> list[Conversation]:
        if self._repository is None:
            return []
        return self._repository.list_conversations()

    def list_conversation_asks(self, conversation_id: UUID) -> list[Ask]:
        if self._repository is None:
            return []
        return self._repository.list_conversation_asks(conversation_id)

    def _ask_events(
        self,
        question: str,
        document_slugs: Sequence[str] | None,
        conversation_id: UUID | None,
    ) -> Iterator[AskEvent]:
        try:
            yield from self._run(question, document_slugs, conversation_id)
        except Exception as exc:
            yield _event(
                AskEventType.ERROR,
                {
                    "message": str(exc),
                    "conversation_id": str(conversation_id) if conversation_id else None,
                },
            )

    def _run(
        self,
        question: str,
        document_slugs: Sequence[str] | None,
        conversation_id: UUID | None,
    ) -> Generator[AskEvent]:
        started = time.perf_counter()
        yield _event(AskEventType.STAGE, {"stage": "retrieving"})

        retrieval = self.retrieve(question, document_slugs=document_slugs)
        yield _event(AskEventType.STAGE, {"stage": "reranking"})

        chunks = retrieval.chunks
        top_score = chunks[0].score if chunks else 0.0

        # Gate A: abstain on weak retrieval, unless the user named a clause we hold.
        has_exact_clause = bool(retrieval.clause_ids) and any(
            matches(c.clause_path, cid) for c in chunks for cid in retrieval.clause_ids
        )
        if not chunks or (not has_exact_clause and top_score < self._tau_retrieval):
            yield from self._emit_abstain(
                AbstentionReason.WEAK_RETRIEVAL, retrieval, started, None, conversation_id
            )
            return

        # Generation.
        yield _event(AskEventType.STAGE, {"stage": "generating"})
        language = detect_language(question)
        valid_ids = chunk_id_set(chunks)
        llm = self._llm
        assert llm is not None  # checked by ask()

        text, usage = yield from self._stream(
            llm, SYSTEM_PROMPT, render_user(question, chunks, language)
        )
        parsed = parse_answer(text)

        # Parse repair (AD-4): one retry, then UNCITED.
        if isinstance(parsed, ParseError):
            text, usage, parsed = yield from self._repair(
                llm, question, chunks, language, parsed.detail
            )
            if isinstance(parsed, ParseError):
                yield from self._emit_abstain(
                    AbstentionReason.UNCITED,
                    retrieval,
                    started,
                    usage,
                    conversation_id,
                    "parse failed after repair",
                )
                return

        # insufficient: the model confirmed the context cannot answer (AD-4 → WEAK_RETRIEVAL).
        if parsed.insufficient:
            yield from self._emit_abstain(
                AbstentionReason.WEAK_RETRIEVAL,
                retrieval,
                started,
                usage,
                conversation_id,
                "insufficient context",
            )
            return

        # Gate B (AD-5): valid chunk ids + ≥1 citation per paragraph; one repair, then UNCITED.
        gate_b = _gate_b(parsed, valid_ids)
        if gate_b is not None:
            text, usage, parsed = yield from self._repair(llm, question, chunks, language, gate_b)
            if isinstance(parsed, ParseError):
                yield from self._emit_abstain(
                    AbstentionReason.UNCITED,
                    retrieval,
                    started,
                    usage,
                    conversation_id,
                    "repair was unparseable",
                )
                return
            if parsed.insufficient:
                yield from self._emit_abstain(
                    AbstentionReason.WEAK_RETRIEVAL,
                    retrieval,
                    started,
                    usage,
                    conversation_id,
                    "insufficient after repair",
                )
                return
            gate_b = _gate_b(parsed, valid_ids)
            if gate_b is not None:
                yield from self._emit_abstain(
                    AbstentionReason.UNCITED, retrieval, started, usage, conversation_id, gate_b
                )
                return

        # Grounded.
        assert isinstance(parsed, ParsedAnswer)
        citations = _ranked_citations(parsed.citations, chunks)
        answer = Answer(
            answer_md=parsed.answer_md,
            citations=citations,
            insufficient=False,
            confidence=top_score,
        )
        usage_eff = usage or TokenUsage(prompt_tokens=0, completion_tokens=0)
        cost = self._cost(usage_eff, llm.model_name)
        latency_ms = int(_ms_since(started))
        yield _event(
            AskEventType.CITATIONS,
            {
                "citations": [c.model_dump(mode="json") for c in citations],
                "answer_md": answer.answer_md,
            },
        )
        ask_row = Ask(
            id=uuid4(),
            question=question,
            status=AskStatus.GROUNDED,
            answer_md=answer.answer_md,
            confidence=top_score,
            latency_ms=latency_ms,
            cost_usd=cost,
            pipeline_debug=self._debug(
                retrieval, usage_eff, latency_ms, top_score, "grounded", None
            ),
            created_at=datetime.now(UTC),
            conversation_id=conversation_id,
        )
        if self._repository is not None:
            self._repository.save_ask(ask_row, citations)
        yield _event(
            AskEventType.FINAL,
            {
                "status": AskStatus.GROUNDED.value,
                "answer": answer.model_dump(mode="json"),
                "usage": usage_eff.model_dump(mode="json"),
                "ask_id": str(ask_row.id),
                "latency_ms": latency_ms,
                "conversation_id": str(conversation_id) if conversation_id else None,
            },
        )

    def _emit_abstain(
        self,
        reason: AbstentionReason,
        retrieval: RetrievalResult,
        started: float,
        usage: TokenUsage | None,
        conversation_id: UUID | None,
        note: str | None = None,
    ) -> Generator[AskEvent]:
        top_passages = tuple(retrieval.chunks[: self._context_k])
        confidence = retrieval.chunks[0].score if retrieval.chunks else None
        abst = Abstention(reason=reason, confidence=confidence, top_passages=top_passages)
        usage_eff = usage or TokenUsage(prompt_tokens=0, completion_tokens=0)
        cost = (
            self._cost(usage_eff, self._llm.model_name)
            if (usage is not None and self._llm is not None)
            else None
        )
        latency_ms = int(_ms_since(started))
        yield _event(
            AskEventType.CITATIONS,
            {
                "citations": [],
                "abstention": True,
                "reason": reason.value,
                "top_passages": [p.model_dump(mode="json") for p in top_passages],
            },
        )
        ask_row = Ask(
            id=uuid4(),
            question=retrieval.question,
            status=AskStatus.ABSTAINED,
            answer_md=None,
            confidence=confidence,
            latency_ms=int(_ms_since(started)),
            cost_usd=cost,
            pipeline_debug=self._debug(
                retrieval, usage_eff, latency_ms, confidence, "abstained", note
            ),
            created_at=datetime.now(UTC),
            conversation_id=conversation_id,
        )
        if self._repository is not None:
            self._repository.save_ask(ask_row, [])
        yield _event(
            AskEventType.FINAL,
            {
                "status": AskStatus.ABSTAINED.value,
                "abstention": abst.model_dump(mode="json"),
                "usage": usage_eff.model_dump(mode="json"),
                "ask_id": str(ask_row.id),
                "latency_ms": latency_ms,
                "conversation_id": str(conversation_id) if conversation_id else None,
            },
        )

    def _stream(
        self, llm: LLMProvider, system: str, user: str
    ) -> Generator[AskEvent, None, tuple[str, TokenUsage]]:
        """Stream the generator, yielding TOKEN events; RETURN (text, usage)."""
        gen = llm.stream(system, user)
        text = ""
        usage = TokenUsage(prompt_tokens=0, completion_tokens=0)
        while True:
            try:
                token = next(gen)
            except StopIteration as stop:
                if stop.value is not None:
                    usage = stop.value
                break
            text += token
            yield _event(AskEventType.TOKEN, {"token": token})
        return text, usage

    def _repair(
        self,
        llm: LLMProvider,
        question: str,
        chunks: tuple[RetrievedChunk, ...],
        language: str,
        critique: str,
    ) -> Generator[AskEvent, None, tuple[str, TokenUsage, ParsedAnswer | ParseError]]:
        """One repair retry (AD-4/AD-5): re-stream with the critique. RETURN parsed too."""
        text, usage = yield from self._stream(
            llm, SYSTEM_PROMPT, render_repair(question, chunks, language, critique)
        )
        return text, usage, parse_answer(text)

    def _cost(self, usage: TokenUsage, model_name: str) -> Decimal | None:
        """Per-call USD (AD-6): only when the model has a price entry, else NULL."""
        price = self._model_prices.get(model_name)
        if price is None:
            return None
        prompt_per_m, completion_per_m = price
        total = (
            Decimal(usage.prompt_tokens) * Decimal(str(prompt_per_m)) / _PER_MILLION
            + Decimal(usage.completion_tokens) * Decimal(str(completion_per_m)) / _PER_MILLION
        )
        return total.quantize(Decimal("0.00001"))

    def _debug(
        self,
        retrieval: RetrievalResult,
        usage: TokenUsage,
        latency_ms: int,
        confidence: float | None,
        status: str,
        note: str | None,
    ) -> dict[str, object]:
        debug: dict[str, object] = dict(retrieval.pipeline_debug)
        debug["status"] = status
        debug["latency_ms"] = latency_ms
        debug["confidence"] = confidence
        debug["usage"] = {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
        }
        if self._reranker is not None:
            debug["model"] = self._llm.model_name if self._llm is not None else None
        if note is not None:
            debug["note"] = note
        return debug


# --- helpers -----------------------------------------------------------------


def _gate_b(parsed: ParsedAnswer, valid_ids: frozenset[str]) -> str | None:
    """Validate the §7 step-6 citation contract (AD-5). None ⇒ ok; else a critique."""
    invalid = [c.chunk_id for c in parsed.citations if c.chunk_id not in valid_ids]
    if invalid:
        return (
            "These cited chunk_ids are not in the provided context: "
            + ", ".join(invalid)
            + ". Cite only ids present in the context."
        )
    paragraphs = [p for p in parsed.answer_md.split("\n\n") if p.strip()]
    if len(parsed.citations) < len(paragraphs):
        return (
            f"Every answer paragraph needs at least one citation; your answer has "
            f"{len(paragraphs)} paragraph(s) and {len(parsed.citations)} citation(s)."
        )
    if paragraphs and not parsed.citations:
        return "The answer has paragraphs but no citations."
    return None


def _ranked_citations(
    raw: Sequence[RawCitation], chunks: tuple[RetrievedChunk, ...]
) -> tuple[Citation, ...]:
    """Map parsed RawCitations → domain Citations with rank + retrieval score."""
    by_id = {str(c.chunk_id): c for c in chunks}
    out: list[Citation] = []
    for rank, rc in enumerate(raw, start=1):
        chunk = by_id.get(rc.chunk_id)
        out.append(
            Citation(
                chunk_id=UUID(rc.chunk_id),
                rank=rank,
                score=chunk.score if chunk is not None else 0.0,
                claim=rc.claim or None,
                clause_path=chunk.clause_path if chunk is not None else None,
            )
        )
    return tuple(out)


def _retrieved(chunk: Chunk, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk.id,
        clause_path=chunk.clause_path,
        content=chunk.content,
        score=score,
    )


def _event(event_type: AskEventType, data: dict[str, object]) -> AskEvent:
    return AskEvent(type=event_type, data=data)


def _ms_since(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)
