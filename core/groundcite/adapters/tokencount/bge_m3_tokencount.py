"""Implements TokenCounter (spec §6, §6.1 #4): bge-m3 token counting via the
transformers AutoTokenizer, so chunk-size limits use the SAME tokenizer as the
configured embedder. Injected into the Chunker as ``count_tokens`` by
``container.py`` — never imported by the chunker directly.

transformers is an optional dependency (``uv sync --extra embed``). The tokenizer
is loaded ONCE and cached at module level (functools.lru_cache) — not reloaded per
call. The bge_m3_embed adapter loads the full FlagModel (with its own internal
tokenizer); the two adapters stay decoupled (no direct import between them,
§6.1 #4) and each caches its own loaded instance.
"""

from __future__ import annotations

from functools import cache
from typing import Any


@cache
def _load_tokenizer(model_name: str) -> Any:
    try:  # pragma: no cover - exercised only when the embed extra is installed
        from transformers import AutoTokenizer  # type: ignore[import-not-found]
    except ImportError as err:  # pragma: no cover
        raise RuntimeError(
            "transformers is not installed. Install the embed extra: `uv sync --extra embed`."
        ) from err
    return AutoTokenizer.from_pretrained(model_name)


class BgeM3TokenCounter:
    """Token counter using the bge-m3 tokenizer (spec §6.1 #4).

    The tokenizer loads lazily on first ``count`` (not in ``__init__``) so
    ``container.build_services`` can construct this adapter even when the embed
    extra is absent (CI); the call site (real ingest) requires the extra.
    """

    def __init__(self, model_name: str = "BAAI/bge-m3") -> None:
        self._model_name = model_name
        self._tokenizer: Any = None  # loaded on first count, cached on the instance

    def count(self, text: str) -> int:
        if self._tokenizer is None:
            self._tokenizer = _load_tokenizer(self._model_name)
        # add_special_tokens=False: chunk content goes into the embedder's
        # encode without special tokens, so the count mirrors what's embedded.
        return len(self._tokenizer.encode(text, add_special_tokens=False))


def make_bge_m3_token_counter(model_name: str = "BAAI/bge-m3") -> BgeM3TokenCounter:
    """Container factory (spec §4 wiring seam)."""
    return BgeM3TokenCounter(model_name=model_name)


class WhitespaceTokenCounter:
    """No-dependency token counter for dry runs (SKIP_EMBEDDINGS). Whitespace
    split is a coarse stand-in for the bge-m3 tokenizer so the ingest pipeline
    can be exercised without configuring the real tokenizer/model. NOT a
    production counter — chunk sizes differ slightly from the real tokenizer.
    """

    def count(self, text: str) -> int:
        return len(text.split())


def make_whitespace_token_counter() -> WhitespaceTokenCounter:
    """Container factory for the SKIP_EMBEDDINGS dry-run path."""
    return WhitespaceTokenCounter()
