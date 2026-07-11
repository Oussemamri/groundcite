"""Composition root — the only place adapters are wired (spec §4).

``build_services(settings)`` selects a concrete adapter per port from config and
injects them into the services. This is the seam that keeps the dependency rule
intact: services and adapters never import each other, they meet only here.

P5 stub: returns the service shells with no adapters wired yet. Real wiring
(embedding/LLM/reranker/store per ``settings``) lands alongside the services in
Weeks 1–4.
"""

from __future__ import annotations

from dataclasses import dataclass

from groundcite.config import Settings
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
    """Build services from config (spec §4 composition root).

    Stub: adapters are not wired yet. When they are, this function will read
    ``settings.embedding_provider`` / ``settings.llm_provider`` /
    ``settings.reranker_enabled`` etc. and construct the matching adapters here.
    """
    _ = settings  # will drive adapter selection in later milestones
    return Services(
        ingestion=IngestionService(),
        ask=AskService(),
        evals=EvalService(),
        library=LibraryService(),
    )
