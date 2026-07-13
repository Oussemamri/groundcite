"""Composition root — the only place adapters are wired (spec §4).

``build_services(settings)`` selects a concrete adapter per port from config and
injects them into the services. This is the seam that keeps the dependency rule
intact: services and adapters never import each other, they meet only here.

Adapters construct lazily (models/tokenizers/DB connections open on first use),
so this function works in CI without the optional extras (pdf/embed) or a live
Postgres — the IngestionService is fully wired but nothing is opened until used.
"""

from __future__ import annotations

from dataclasses import dataclass

from groundcite.adapters.chunker.clause_chunker import make_clause_chunker
from groundcite.adapters.embedding.bge_m3_embed import make_bge_m3_embedder, make_zero_embedder
from groundcite.adapters.lexical.pg_lexical import make_pg_lexical_index
from groundcite.adapters.parser.pymupdf_parser import make_pymupdf_parser
from groundcite.adapters.repository.pg_repo import make_pg_repository
from groundcite.adapters.reranker.bge_reranker import make_bge_reranker
from groundcite.adapters.structure.cfr_structure import make_cfr_structure_detector
from groundcite.adapters.tokencount.bge_m3_tokencount import (
    make_bge_m3_token_counter,
    make_whitespace_token_counter,
)
from groundcite.adapters.vector.pg_vector import make_pg_vector_index
from groundcite.config import Settings
from groundcite.ports.protocols import EmbeddingProvider, Reranker, TokenCounter
from groundcite.services import (
    AskService,
    EvalService,
    IngestionService,
    LibraryService,
)


@dataclass(frozen=True)
class Services:
    """The wired application services handed to the interface layer (spec §4)."""

    ingestion: IngestionService
    ask: AskService
    evals: EvalService
    library: LibraryService


def build_services(settings: Settings) -> Services:
    """Build services from config (spec §4 composition root)."""
    # The parser and structure detector are dep-free; always wired.
    parser = make_pymupdf_parser()
    detector = make_cfr_structure_detector()
    chunker = make_clause_chunker(min_leaf_tokens=settings.min_leaf_tokens)

    # SKIP_EMBEDDINGS = a true no-model dry run: zero-vector embeddings AND a
    # no-dependency whitespace token counter, so the pipeline runs without the
    # embed extra. Production uses the real bge-m3 tokenizer in lockstep.
    token_counter: TokenCounter
    if settings.skip_embeddings:
        token_counter = make_whitespace_token_counter()
    else:
        token_counter = make_bge_m3_token_counter(model_name=settings.embedding_model)

    # Embedding: real bge-m3, or zero-vector dry-run when SKIP_EMBEDDINGS.
    embedder: EmbeddingProvider
    if settings.skip_embeddings:
        embedder = make_zero_embedder()
    else:
        embedder = make_bge_m3_embedder(model_name=settings.embedding_model)

    repository = make_pg_repository(settings.database_url)

    # Retrieval (spec §7): both indexes read the same chunks table; the reranker
    # is optional — RERANKER_ENABLED=false wires None, which turns stage [3] off
    # in AskService rather than hiding a no-op adapter behind the port.
    vector_index = make_pg_vector_index(settings.database_url)
    lexical_index = make_pg_lexical_index(settings.database_url)
    reranker: Reranker | None = (
        make_bge_reranker(model_name=settings.reranker_model) if settings.reranker_enabled else None
    )

    return Services(
        ingestion=IngestionService(
            parser=parser,
            detector=detector,
            chunker=chunker,
            embedder=embedder,
            token_counter=token_counter,
            repository=repository,
        ),
        ask=AskService(
            embedder=embedder,
            vector_index=vector_index,
            lexical_index=lexical_index,
            reranker=reranker,
            rrf_k=settings.rrf_k,
            candidates_dense=settings.candidates_dense,
            candidates_lexical=settings.candidates_lexical,
            fused_k=settings.fused_k,
            context_k=settings.context_k,
        ),
        evals=EvalService(),
        library=LibraryService(),
    )
