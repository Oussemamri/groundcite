"""AskService — the retrieval → gate → generate → gate pipeline (spec §7).

Implements spec §7 ``AskService.ask(question, filters) -> stream of AskEvents``:
clause-ID detection, dense + lexical + clause fast-path candidates, RRF fusion,
optional rerank, Gate A (retrieval), generation, Gate B (citation validity),
persist + stream. Not yet implemented (Weeks 2–3). Depends on the retrieval,
reranker, LLM and repository ports.
"""

from __future__ import annotations


class AskService:
    """Resolve one Ask into a grounded Answer or a first-class Abstention (spec §7)."""
