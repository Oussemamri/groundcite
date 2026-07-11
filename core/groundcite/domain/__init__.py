"""Domain layer (spec §4).

Pure Python, zero I/O. Pydantic v2 **frozen** models expressing the ubiquitous
language of spec §2.1: ``Document``, ``Section``, ``Chunk``, ``Ask``,
``Answer``, ``Citation``, ``Abstention``/``AbstentionReason``, ``EvalCase``.
This layer imports nothing internal.
"""

from groundcite.domain.entities import (
    Ask,
    Chunk,
    Document,
    EvalCase,
    ParsedBlock,
    ParsedDocument,
    ParsedPage,
    Section,
)
from groundcite.domain.results import (
    Abstention,
    AbstentionReason,
    Answer,
    AskEvent,
    AskEventType,
    AskStatus,
    Citation,
    EvalResult,
    EvalRun,
    RetrievedChunk,
    Stage,
)

__all__ = [
    "Abstention",
    "AbstentionReason",
    "Answer",
    "Ask",
    "AskEvent",
    "AskEventType",
    "AskStatus",
    "Chunk",
    "Citation",
    "Document",
    "EvalCase",
    "EvalResult",
    "EvalRun",
    "ParsedBlock",
    "ParsedDocument",
    "ParsedPage",
    "RetrievedChunk",
    "Section",
    "Stage",
]
