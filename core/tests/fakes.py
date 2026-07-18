"""Fake ports for unit tests (spec §17 rule 3: no network, no DB, no models).

Deterministic, no third-party deps. Used by service-layer tests so the suite
runs without the pdf/embed extras or a live Postgres.
"""

from __future__ import annotations

from collections.abc import Generator, Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from groundcite.domain.entities import Ask, Chunk, Conversation, Document, EvalCase, Section
from groundcite.domain.results import Citation, EvalResult, EvalRun, TokenUsage
from groundcite.ports.protocols import Vector

# A dense embedding vector the chunk store will actually use (1024-d), so fake
# embeddings exercise the same shape as the real bge-m3 adapter.
_FAKE_DIM = 1024


class FakeEmbedder:
    """Returns deterministic 1024-d zero vectors (no model load)."""

    def __init__(self, dimension: int = _FAKE_DIM) -> None:
        self._dim = dimension

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        zero = tuple(0.0 for _ in range(self._dim))
        return [zero for _ in texts]


class FakeTokenCounter:
    """Whitespace token counter — deterministic, no tokenizer library."""

    def count(self, text: str) -> int:
        return len(text.split())


class FakeVectorIndex:
    """Dense index returning a scripted, already-ranked candidate list."""

    def __init__(self, results: Sequence[tuple[Chunk, float]] | None = None) -> None:
        self.results = list(results or ())
        self.calls: list[tuple[int, tuple[str, ...]]] = []

    def search(
        self,
        embedding: Vector,
        top_k: int,
        document_slugs: Sequence[str] | None = None,
    ) -> list[tuple[Chunk, float]]:
        self.calls.append((top_k, tuple(document_slugs or ())))
        return self.results[:top_k]


class FakeLexicalIndex:
    """Lexical index + clause fast path, both scripted.

    ``clause_hits`` maps a clause id ("25.1309(b)") to the chunks the exact-match
    fast path returns for it.
    """

    def __init__(
        self,
        results: Sequence[tuple[Chunk, float]] | None = None,
        clause_hits: dict[str, list[Chunk]] | None = None,
    ) -> None:
        self.results = list(results or ())
        self.clause_hits = clause_hits or {}
        self.searched: list[str] = []
        self.matched: list[str] = []

    def search(
        self,
        query: str,
        top_k: int,
        document_slugs: Sequence[str] | None = None,
    ) -> list[tuple[Chunk, float]]:
        self.searched.append(query)
        return self.results[:top_k]

    def match_clause(
        self, clause_path: str, document_slugs: Sequence[str] | None = None
    ) -> list[Chunk]:
        self.matched.append(clause_path)
        return list(self.clause_hits.get(clause_path, ()))


class FakeReranker:
    """Cross-encoder stand-in: reorders candidates by a scripted score per
    clause_path (unlisted chunks score 0.0). No model, no torch."""

    def __init__(self, scores: dict[str, float] | None = None) -> None:
        self.scores = scores or {}
        self.calls: list[tuple[str, int]] = []

    def rerank(
        self, question: str, candidates: Sequence[Chunk], top_k: int
    ) -> list[tuple[Chunk, float]]:
        self.calls.append((question, top_k))
        scored = [(c, self.scores.get(c.clause_path, 0.0)) for c in candidates]
        scored.sort(key=lambda pair: (-pair[1], pair[0].clause_path))
        return scored[:top_k]


class FakeLLM:
    """Scripted token stream + scripted usage (no network, no model).

    Mirrors the real ``LLMProvider`` contract: ``stream`` is a generator that
    yields token strings and RETURNS the per-call ``TokenUsage`` as its
    ``StopIteration`` value (AD-1). Used by the ask()/eval unit tests so the
    service suite runs without the llm extra.

    ``responses`` may be a single string (reused every call — happy path) or a
    list of strings, one per successive call, so the Phase-4 repair-retry tests
    can script the first call to FAIL Gate B and the second to pass. Tokens are
    yielded one CHARACTER at a time to exercise the streaming token loop. When
    ``responses`` is exhausted on a later call, the last response is reused.
    """

    def __init__(
        self,
        responses: str | Sequence[str] | None = None,
        usages: TokenUsage | Sequence[TokenUsage] | None = None,
    ) -> None:
        # model_name mirrors the OpenAICompatibleLLM port (AD-1); feeds the
        # eval config snapshot + cost lookup in the fake-LLM tests.
        self.model_name: str = "fake-model"
        if isinstance(responses, str):
            self._responses: list[str] = [responses]
        else:
            self._responses = list(responses or ())
        if usages is None:
            default = TokenUsage(prompt_tokens=10, completion_tokens=20)
            self._usages: list[TokenUsage] = [default]
        elif isinstance(usages, TokenUsage):
            self._usages = [usages]
        else:
            self._usages = list(usages)
        self.calls: list[tuple[str, str]] = []

    def stream(self, system: str, user: str) -> Generator[str, None, TokenUsage]:
        call_idx = len(self.calls)
        self.calls.append((system, user))
        if not self._responses:
            text = ""
        else:
            text = self._responses[min(call_idx, len(self._responses) - 1)]
        usage = self._usages[min(call_idx, len(self._usages) - 1)]
        yield from text  # text is a str → one char per streamed token (exercises the loop)
        return usage


class FakeRepository:
    """In-memory Repository for IngestionService unit tests.

    ``replace_sections_and_chunks`` replaces in one logical transaction (spec §6
    idempotency): rows for a document are overwritten so re-ingesting a slug
    leaves counts unchanged.
    """

    def __init__(self) -> None:
        self.documents: dict[str, Document] = {}
        self.sections: dict[str, list[Section]] = {}
        self.chunks: dict[str, list[Chunk]] = {}
        self.asks: dict[UUID, Ask] = {}
        self.citations: dict[UUID, list[Citation]] = {}
        self.conversations: dict[UUID, Conversation] = {}
        self.eval_cases: dict[UUID, EvalCase] = {}
        self.eval_runs: dict[UUID, EvalRun] = {}
        self.eval_results: dict[UUID, list[EvalResult]] = {}
        self.replace_calls: int = 0

    def upsert_document(self, document: Document) -> Document:
        existing = self.documents.get(document.slug)
        if existing:
            # Preserve the canonical id on slug conflict (mirrors the pg_repo
            # ON CONFLICT … RETURNING id), so re-ingest keeps the same id.
            kept = existing.model_copy(
                update={
                    "standard_code": document.standard_code,
                    "title": document.title,
                    "organization": document.organization,
                    "version": document.version,
                    "language": document.language,
                    "source_url": document.source_url,
                    "license_note": document.license_note,
                }
            )
            self.documents[document.slug] = kept
            return kept
        self.documents[document.slug] = document
        return document

    def get_document(self, slug: str) -> Document | None:
        return self.documents.get(slug)

    def list_documents(self) -> list[Document]:
        return list(self.documents.values())

    def replace_sections_and_chunks(
        self, document_id: UUID, sections: Sequence[Section], chunks: Sequence[Chunk]
    ) -> None:
        self.replace_calls += 1
        slug = next((s for s, d in self.documents.items() if d.id == document_id), None)
        if slug is None:
            raise KeyError(f"no document for id {document_id}")
        self.sections[slug] = list(sections)
        self.chunks[slug] = list(chunks)

    def get_section_tree(self, document_id: UUID) -> list[Section]:
        slug = next((s for s, d in self.documents.items() if d.id == document_id), None)
        return list(self.sections.get(slug, ())) if slug else []

    def get_chunk(self, chunk_id: UUID) -> Chunk | None:
        for clist in self.chunks.values():
            for c in clist:
                if c.id == chunk_id:
                    return c
        return None

    def list_chunks(self, document_id: UUID) -> list[Chunk]:
        slug = next((s for s, d in self.documents.items() if d.id == document_id), None)
        if not slug:
            return []
        return sorted(self.chunks.get(slug, ()), key=lambda c: c.clause_path)

    def save_ask(self, ask: Ask, citations: Sequence[Citation]) -> None:
        self.asks[ask.id] = ask
        self.citations[ask.id] = list(citations)

    def get_ask(self, ask_id: UUID) -> Ask | None:
        return self.asks.get(ask_id)

    def get_ask_citations(self, ask_id: UUID) -> list[Citation]:
        # Citation.clause_path/claim are already materialized at save time on the
        # FakeRepository (no chunks join needed); order by rank (spec §9 replay).
        return sorted(self.citations.get(ask_id, ()), key=lambda c: c.rank)

    def create_conversation(self, title: str) -> Conversation:
        conv = Conversation(id=uuid4(), title=title, created_at=datetime.now(UTC))
        self.conversations[conv.id] = conv
        return conv

    def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        return self.conversations.get(conversation_id)

    def list_conversations(self) -> list[Conversation]:
        # Newest first: insertion order reversed (same pattern as
        # list_eval_runs) -- avoids sorting by created_at, which would be a
        # timing-flaky and naive/aware-datetime-comparison-fragile substitute
        # for "the order conversations were actually created in."
        out = []
        for conv in reversed(list(self.conversations.values())):
            asks = [a for a in self.asks.values() if a.conversation_id == conv.id]
            latest = max(
                asks, key=lambda a: a.created_at or datetime.min.replace(tzinfo=UTC), default=None
            )
            out.append(
                conv.model_copy(
                    update={
                        "turn_count": len(asks),
                        "latest_status": latest.status if latest else None,
                    }
                )
            )
        return out

    def list_conversation_asks(self, conversation_id: UUID) -> list[Ask]:
        asks = [a for a in self.asks.values() if a.conversation_id == conversation_id]
        return sorted(asks, key=lambda a: a.created_at or datetime.min.replace(tzinfo=UTC))

    def load_suite(self, suite: str) -> list[EvalCase]:
        return []

    def save_eval_run(
        self, run: EvalRun, cases: Sequence[EvalCase], results: Sequence[EvalResult]
    ) -> None:
        for case in cases:
            self.eval_cases[case.id] = case
        self.eval_runs[run.id] = run
        self.eval_results[run.id] = list(results)

    def get_eval_run(self, run_id: UUID) -> EvalRun | None:
        return self.eval_runs.get(run_id)

    def get_eval_results(self, run_id: UUID) -> list[EvalResult]:
        return list(self.eval_results.get(run_id, ()))

    def list_eval_runs(self) -> list[EvalRun]:
        # Newest first: insertion order reversed mirrors ``eval_runs ORDER BY
        # started_at DESC`` (runs are inserted in order of execution).
        return list(reversed(self.eval_runs.values()))

    def get_eval_cases(self, case_ids: Sequence[UUID]) -> dict[UUID, EvalCase]:
        return {cid: self.eval_cases[cid] for cid in case_ids if cid in self.eval_cases}
