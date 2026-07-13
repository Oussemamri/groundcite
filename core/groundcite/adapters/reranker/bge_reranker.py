"""Implements Reranker (spec §7 step 3, §11 default): bge-reranker-v2-m3 cross-encoder.

Wraps AnswerDotAI's ``rerankers`` — spec §11 is explicit that "our Reranker port
wraps it". The cross-encoder reads (question, chunk) TOGETHER, unlike the
bi-encoder embeddings which never see the two at once, so it is the big precision
win on the top-20 (§11) at a cost that is affordable only because fusion already
cut the field from thousands of chunks down to 20.

Scores are NORMALIZED to [0, 1] (spec §11: "normalize=True reranker scores feed
τ_retrieval"), which is what makes ``TAU_RETRIEVAL=0.35`` a meaningful constant in
Gate A (Week 3) rather than a magic number pinned to some raw logit scale.

``rerankers`` is an optional dependency — ``uv sync --extra rerank`` (it pulls
torch). The import is lazy/guarded so CI (no extras) and the unit suite
(FakeReranker) never need it, matching the bge_m3_embed adapter's pattern.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from groundcite.domain.entities import Chunk

try:  # pragma: no cover - exercised only when the rerank extra is installed
    from rerankers import Reranker as _RerankersFactory  # type: ignore[import]
except ImportError:  # pragma: no cover
    _RerankersFactory = None


class BgeReranker:
    """Cross-encoder reranker implementing the Reranker port (spec §7 step 3).

    The model loads lazily on first ``rerank`` (not in ``__init__``) so
    ``container.build_services`` can construct this adapter without the extra
    installed; only an actual rerank call requires it.
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3") -> None:
        self._model_name = model_name
        self._model: Any = None  # loaded on first rerank, cached on the instance

    def _load(self) -> Any:
        if self._model is None:
            if _RerankersFactory is None:  # pragma: no cover - guarded by import
                raise RuntimeError(
                    "`rerankers` is not installed. Install the rerank extra "
                    "(`uv sync --extra rerank`), or set RERANKER_ENABLED=false."
                )
            self._model = _RerankersFactory(self._model_name, model_type="cross-encoder")
        return self._model

    def rerank(
        self, question: str, candidates: Sequence[Chunk], top_k: int
    ) -> list[tuple[Chunk, float]]:
        """Reorder ``candidates`` by cross-encoder relevance, best first."""
        if not candidates or top_k <= 0:
            return []
        model = self._load()
        ranked = model.rank(
            query=question,
            docs=[c.content for c in candidates],
            doc_ids=list(range(len(candidates))),
        )
        out: list[tuple[Chunk, float]] = [
            (candidates[int(r.doc_id)], float(r.score)) for r in ranked.results
        ]
        # `rerankers` returns results best-first, but sort defensively so the
        # port's contract (descending score) holds for whichever backend it wraps.
        out.sort(key=lambda pair: -pair[1])
        return out[:top_k]


def make_bge_reranker(model_name: str = "BAAI/bge-reranker-v2-m3") -> BgeReranker:
    """Container factory (spec §4 wiring seam)."""
    return BgeReranker(model_name=model_name)
