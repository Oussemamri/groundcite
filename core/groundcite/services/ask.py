"""AskService — the retrieval → gate → generate → gate pipeline (spec §7).

Week 2 implements the RETRIEVAL half, as a first-class, LLM-free entry point:

    retrieve(question, document_slugs) -> RetrievalResult      # steps 0-3

    [0]  clause-ID detection            (services/clause_detect)
    [1a] dense candidates    top-30     (VectorIndex, cosine/HNSW)
    [1b] lexical candidates  top-30     (LexicalIndex, ts_rank_cd)
    [1c] clause fast path               (LexicalIndex.match_clause) — rank 1
    [2]  RRF fusion          top-20     (services/fusion)
    [3]  rerank (optional)   top-6      (Reranker)

``retrieve`` is deliberately generation-free and takes no LLM port. That is a
structural requirement, not a convenience: spec §8 scores retrieval with
recall@k / MRR and calls retrieval-only cases "the most stable CI signal", so
EvalService must be able to measure retrieval WITHOUT invoking a judge or an
answerer. Week 3's ``ask()`` (Gate A → generate → Gate B → stream AskEvents)
calls this same method and adds the generation half on top.

Everything here is orchestration over injected ports — no adapter imports, no
config import (spec §4 dependency rule).
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from groundcite.domain.entities import Chunk
from groundcite.domain.results import RetrievalResult, RetrievedChunk
from groundcite.ports.protocols import (
    EmbeddingProvider,
    LexicalIndex,
    Reranker,
    VectorIndex,
)
from groundcite.services.clause_detect import detect_clause_ids
from groundcite.services.fusion import fuse


class AskService:
    """Resolve one Ask into a grounded Answer or a first-class Abstention (spec §7).

    Week 2: ``retrieve`` only. Generation and Gates A/B arrive in Week 3.
    """

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


def _retrieved(chunk: Chunk, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk.id,
        clause_path=chunk.clause_path,
        content=chunk.content,
        score=score,
    )


def _ms_since(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)
