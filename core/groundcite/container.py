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
from groundcite.adapters.parser.pymupdf_parser import make_pymupdf_parser
from groundcite.adapters.repository.pg_repo import make_pg_repository
from groundcite.adapters.structure.cfr_structure import make_cfr_structure_detector
from groundcite.adapters.tokencount.bge_m3_tokencount import make_bge_m3_token_counter
from groundcite.config import Settings
from groundcite.ports.protocols import EmbeddingProvider
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
    token_counter = make_bge_m3_token_counter(model_name=settings.embedding_model)

    # Embedding: real bge-m3, or zero-vector dry-run when SKIP_EMBEDDINGS.
    embedder: EmbeddingProvider
    if settings.skip_embeddings:
        embedder = make_zero_embedder()
    else:
        embedder = make_bge_m3_embedder(model_name=settings.embedding_model)

    repository = make_pg_repository(settings.database_url)

    return Services(
        ingestion=IngestionService(
            parser=parser,
            detector=detector,
            chunker=chunker,
            embedder=embedder,
            token_counter=token_counter,
            repository=repository,
        ),
        ask=AskService(),
        evals=EvalService(),
        library=LibraryService(),
    )
