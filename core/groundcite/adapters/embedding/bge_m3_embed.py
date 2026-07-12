"""Implements EmbeddingProvider (spec §11 default): BAAI/bge-m3, 1024-d
multilingual (DE<->EN), local and free, via FlagEmbedding.

FlagEmbedding is an optional dependency — ``uv sync --extra embed``. The import
is lazy (module-level guarded) so CI (no extras) and unit tests (FakeEmbedder)
never need it. Construction loads the model once (cached on the instance); encode
is batched to bound memory.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from groundcite.ports.protocols import Vector

try:  # pragma: no cover - exercised only when the embed extra is installed
    from FlagEmbedding import BGEM3FlagModel  # type: ignore[import]
except ImportError:  # pragma: no cover
    BGEM3FlagModel = None

# bge-m3 dense dim is fixed at 1024 (spec §5, §11, prep task P4); locked.
_DIMENSION = 1024
# Encode sub-batch size (bounds peak memory on CPU/local GPU).
_BATCH_SIZE = 32


class BgeM3Embedder:
    """Local bge-m3 embedder implementing EmbeddingProvider (spec §11 default).

    The FlagModel loads lazily on first ``embed`` (not in ``__init__``) so
    ``container.build_services`` can construct this adapter even when the embed
    extra is absent (CI); the call site (real ingest) requires the extra.
    """

    def __init__(self, model_name: str = "BAAI/bge-m3") -> None:
        self._model_name = model_name
        self._model: Any = None  # loaded on first embed, cached on the instance

    @property
    def dimension(self) -> int:
        return _DIMENSION

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        if not texts:
            return []
        if self._model is None:
            if BGEM3FlagModel is None:  # pragma: no cover
                raise RuntimeError(
                    "FlagEmbedding is not installed. Install the embed extra: "
                    "`uv sync --extra embed`."
                )
            self._model = BGEM3FlagModel(self._model_name, use_fp16=True)
        out: list[Vector] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            batch = list(texts[start : start + _BATCH_SIZE])
            res = self._model.encode(batch, batch_size=len(batch), max_length=8192)
            vecs = res["dense_vecs"]
            import numpy as np  # type: ignore

            for row in vecs:
                out.append(tuple(float(x) for x in np.asarray(row).tolist()))
        return out


class ZeroEmbedder:
    """Dry-run embedder (spec task 2e SKIP_EMBEDDINGS): returns 1024-d zero
    vectors so ``chunks.embedding`` (NOT NULL) still has a value while skipping
    the model load. Retrieval is meaningless — this is an ingest-path dry run."""

    def __init__(self) -> None:
        self._dim = _DIMENSION

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        zero = tuple(0.0 for _ in range(self._dim))
        return [zero for _ in texts]


def make_bge_m3_embedder(model_name: str = "BAAI/bge-m3") -> BgeM3Embedder:
    """Container factory (spec §4 wiring seam)."""
    return BgeM3Embedder(model_name=model_name)


def make_zero_embedder() -> ZeroEmbedder:
    """Container factory for the SKIP_EMBEDDINGS dry-run path (spec task 2e)."""
    return ZeroEmbedder()
