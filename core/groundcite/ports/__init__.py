"""Ports layer (spec §4).

Protocol classes defining the seams between services and the outside world —
the build-vs-buy boundary (spec §11). Everything swappable (embeddings, LLM,
reranker, vector/lexical store, parser, chunker, persistence) lives behind one
of these Protocols. Ports import ``domain`` only, and never use ``Any``.
"""

from groundcite.ports.protocols import (
    Chunker,
    DocumentParser,
    EmbeddingProvider,
    LexicalIndex,
    LLMProvider,
    Repository,
    Reranker,
    Vector,
    VectorIndex,
)

__all__ = [
    "Chunker",
    "DocumentParser",
    "EmbeddingProvider",
    "LLMProvider",
    "LexicalIndex",
    "Repository",
    "Reranker",
    "Vector",
    "VectorIndex",
]
