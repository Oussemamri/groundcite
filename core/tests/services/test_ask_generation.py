"""Unit tests for AskService.ask — generation, Gates A/B (spec §7, §17 rule 3).

Fake ports only — no DB, no network, no model. Pins the orchestration Week 3
adds on top of Week 2's ``retrieve`` (AD-2): Gate A (AD-3), the parse/citation
repair retries (AD-4/AD-5), persistence (AD-6), cost accounting, and the exact
AskEvent sequence the SSE contract (spec §7) promises apps/api and apps/web.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from groundcite.domain.entities import Chunk
from groundcite.domain.results import (
    AbstentionReason,
    AskEventType,
    AskStatus,
    TokenUsage,
)
from groundcite.services.ask import AskService
from tests.fakes import (
    FakeEmbedder,
    FakeLexicalIndex,
    FakeLLM,
    FakeRepository,
    FakeReranker,
    FakeVectorIndex,
)


def _chunk(clause: str) -> Chunk:
    return Chunk(
        id=uuid4(),
        document_id=UUID(int=1),
        section_id=UUID(int=2),
        clause_path=f"14 CFR Part 25 §{clause}",
        content=f"body of {clause}",
        token_count=10,
    )


def _valid_json(chunk: Chunk, answer: str = "The answer.") -> str:
    return (
        f'{{"answer_md": "{answer}", "citations": '
        f'[{{"chunk_id": "{chunk.id}", "claim": "grounding claim"}}], "insufficient": false}}'
    )


def _insufficient_json() -> str:
    return (
        '{"answer_md": "Cannot answer from the given context.", '
        '"citations": [], "insufficient": true}'
    )


def _service(
    dense: list[tuple[Chunk, float]] | None = None,
    lexical: list[tuple[Chunk, float]] | None = None,
    clause_hits: dict[str, list[Chunk]] | None = None,
    reranker_scores: dict[str, float] | None = None,
    reranker: FakeReranker | None | bool = False,
    llm_responses: str | list[str] | None = None,
    llm_usages: TokenUsage | list[TokenUsage] | None = None,
    repository: FakeRepository | None | bool = False,
    tau_retrieval: float = 0.35,
    model_prices: dict[str, tuple[float, float]] | None = None,
    context_k: int = 6,
) -> tuple[AskService, FakeRepository, FakeLLM | None]:
    """Build an AskService wired for ask() tests.

    ``reranker=False`` (default) builds a FakeReranker from ``reranker_scores``
    (ask() REQUIRES a reranker, AD-3); pass ``reranker=None`` explicitly to test
    that requirement. ``repository=False`` builds a fresh FakeRepository; pass
    ``repository=None`` to test the optional-persistence path.
    """
    vec = FakeVectorIndex(dense or [])
    lex = FakeLexicalIndex(lexical or [], clause_hits or {})
    rr: FakeReranker | None = FakeReranker(reranker_scores or {}) if reranker is False else reranker  # type: ignore[assignment]
    llm = FakeLLM(llm_responses, llm_usages) if llm_responses is not None else None
    repo: FakeRepository | None = FakeRepository() if repository is False else repository  # type: ignore[assignment]
    svc = AskService(
        embedder=FakeEmbedder(),
        vector_index=vec,
        lexical_index=lex,
        reranker=rr,
        llm=llm,
        tau_retrieval=tau_retrieval,
        repository=repo,
        model_prices=model_prices,
        context_k=context_k,
    )
    return svc, repo, llm  # type: ignore[return-value]


# --- config errors (AD-1/AD-3) ------------------------------------------------


def test_ask_without_llm_raises_at_call_time() -> None:
    c = _chunk("25.1")
    svc, _, _ = _service(dense=[(c, 0.9)], reranker_scores={c.clause_path: 0.9})
    with pytest.raises(RuntimeError, match="LLM provider"):
        svc.ask("What does §25.1 say?")


def test_ask_without_reranker_raises_at_call_time() -> None:
    svc, _, _ = _service(
        dense=[(_chunk("25.1"), 0.9)],
        reranker=None,
        llm_responses="irrelevant",
    )
    with pytest.raises(RuntimeError, match="reranker"):
        svc.ask("What does §25.1 say?")


# --- Gate A (AD-3) -------------------------------------------------------------


def test_gate_a_abstains_on_weak_retrieval() -> None:
    c = _chunk("25.999")
    svc, repo, _ = _service(
        dense=[(c, 0.9)],
        reranker_scores={c.clause_path: 0.10},  # below tau=0.35
        llm_responses="never reached",
        tau_retrieval=0.35,
    )
    events = list(svc.ask("What failure probability is acceptable?"))

    final = events[-1]
    assert final.type is AskEventType.FINAL
    assert final.data["status"] == AskStatus.ABSTAINED.value
    assert final.data["abstention"]["reason"] == AbstentionReason.WEAK_RETRIEVAL.value
    # top_passages carries the weak candidate — abstention is still useful (spec §7).
    assert len(final.data["abstention"]["top_passages"]) == 1
    assert not any(e.type is AskEventType.TOKEN for e in events), "must not generate below tau"
    assert repo.asks, "abstentions are persisted too (AD-6)"
    saved = next(iter(repo.asks.values()))
    assert saved.status is AskStatus.ABSTAINED
    assert repo.citations[saved.id] == []


def test_gate_a_abstains_when_no_chunks_at_all() -> None:
    svc, _, _ = _service(dense=[], lexical=[], llm_responses="never reached")
    events = list(svc.ask("Anything?"))
    assert events[-1].data["abstention"]["reason"] == AbstentionReason.WEAK_RETRIEVAL.value


def test_clause_fast_path_bypasses_gate_a_even_at_low_reranker_score() -> None:
    """An exact clause match in the FINAL context bypasses tau by construction
    (AD-3) — even if the cross-encoder itself scores that chunk low."""
    c = _chunk("25.1309(b)")
    svc, _, llm = _service(
        dense=[(c, 0.9)],
        clause_hits={"25.1309(b)": [c]},
        reranker_scores={c.clause_path: 0.02},  # deliberately far below tau
        llm_responses=_valid_json(c),
        tau_retrieval=0.35,
    )
    events = list(svc.ask("What does §25.1309(b) require?"))

    assert events[-1].data["status"] == AskStatus.GROUNDED.value
    assert llm is not None and len(llm.calls) == 1, "must have reached generation"


# --- happy path + persistence (AD-6) -------------------------------------------


def test_happy_path_grounded_persists_ask_and_citations() -> None:
    c = _chunk("25.1309(b)")
    svc, repo, llm = _service(
        dense=[(c, 0.9)],
        reranker_scores={c.clause_path: 0.95},
        llm_responses=_valid_json(
            c, "Catastrophic failure conditions must be extremely improbable."
        ),
    )
    events = list(svc.ask("What does §25.1309(b) require?"))

    stages = [e.data["stage"] for e in events if e.type is AskEventType.STAGE]
    assert stages == ["retrieving", "reranking", "generating"]
    tokens = "".join(e.data["token"] for e in events if e.type is AskEventType.TOKEN)
    assert tokens == llm.calls[0][1] or len(tokens) > 0  # streamed char-by-char

    final = events[-1]
    assert final.type is AskEventType.FINAL
    assert final.data["status"] == AskStatus.GROUNDED.value
    assert "extremely improbable" in final.data["answer"]["answer_md"]

    assert len(repo.asks) == 1
    saved = next(iter(repo.asks.values()))
    assert saved.status is AskStatus.GROUNDED
    assert saved.answer_md is not None and "extremely improbable" in saved.answer_md
    cites = repo.citations[saved.id]
    assert len(cites) == 1
    assert cites[0].chunk_id == c.id
    assert cites[0].rank == 1
    assert cites[0].clause_path == c.clause_path


def test_persistence_is_skipped_when_no_repository_wired() -> None:
    c = _chunk("25.1")
    svc, _, _ = _service(
        dense=[(c, 0.9)],
        reranker_scores={c.clause_path: 0.9},
        llm_responses=_valid_json(c),
        repository=None,
    )
    events = list(svc.ask("q?"))  # must not raise even though repository is None
    assert events[-1].data["status"] == AskStatus.GROUNDED.value


# --- insufficient mapping (AD-4) ------------------------------------------------


def test_insufficient_flag_maps_to_weak_retrieval_abstention() -> None:
    c = _chunk("25.1")
    svc, repo, _ = _service(
        dense=[(c, 0.9)],
        reranker_scores={c.clause_path: 0.9},  # passes Gate A
        llm_responses=_insufficient_json(),
    )
    events = list(svc.ask("An unrelated question the chunk can't answer"))
    final = events[-1]
    assert final.data["status"] == AskStatus.ABSTAINED.value
    assert final.data["abstention"]["reason"] == AbstentionReason.WEAK_RETRIEVAL.value
    saved = next(iter(repo.asks.values()))
    assert saved.status is AskStatus.ABSTAINED


# --- parse repair (AD-4) --------------------------------------------------------


def test_malformed_json_repairs_then_succeeds() -> None:
    c = _chunk("25.1")
    svc, repo, llm = _service(
        dense=[(c, 0.9)],
        reranker_scores={c.clause_path: 0.9},
        llm_responses=["not json at all", _valid_json(c, "Fixed answer.")],
    )
    events = list(svc.ask("q?"))
    assert events[-1].data["status"] == AskStatus.GROUNDED.value
    assert llm is not None and len(llm.calls) == 2, "one repair retry (AD-4)"
    assert "Fixed answer." in events[-1].data["answer"]["answer_md"]
    assert repo.asks, "the repaired, successful answer is persisted"


def test_malformed_json_repair_also_fails_aborts_uncited() -> None:
    c = _chunk("25.1")
    svc, repo, llm = _service(
        dense=[(c, 0.9)],
        reranker_scores={c.clause_path: 0.9},
        llm_responses=["not json", "still not json"],
    )
    events = list(svc.ask("q?"))
    final = events[-1]
    assert final.data["status"] == AskStatus.ABSTAINED.value
    assert final.data["abstention"]["reason"] == AbstentionReason.UNCITED.value
    assert llm is not None and len(llm.calls) == 2, "exactly one repair retry, then abstain"
    saved = next(iter(repo.asks.values()))
    assert saved.status is AskStatus.ABSTAINED


# --- Gate B: citation validity (AD-5) -------------------------------------------


def test_invalid_citation_repairs_then_succeeds() -> None:
    c = _chunk("25.1")
    bad_json = (
        '{"answer_md": "An answer.", "citations": '
        '[{"chunk_id": "not-a-real-id", "claim": "x"}], "insufficient": false}'
    )
    svc, repo, llm = _service(
        dense=[(c, 0.9)],
        reranker_scores={c.clause_path: 0.9},
        llm_responses=[bad_json, _valid_json(c, "Corrected, cites the real chunk.")],
    )
    events = list(svc.ask("q?"))
    assert events[-1].data["status"] == AskStatus.GROUNDED.value
    assert llm is not None and len(llm.calls) == 2
    saved = next(iter(repo.asks.values()))
    assert repo.citations[saved.id][0].chunk_id == c.id


def test_invalid_citation_repair_still_invalid_aborts_uncited() -> None:
    c = _chunk("25.1")
    bad_json = (
        '{"answer_md": "An answer.", "citations": '
        '[{"chunk_id": "still-fake", "claim": "x"}], "insufficient": false}'
    )
    svc, _, llm = _service(
        dense=[(c, 0.9)],
        reranker_scores={c.clause_path: 0.9},
        llm_responses=[bad_json, bad_json],
    )
    events = list(svc.ask("q?"))
    final = events[-1]
    assert final.data["status"] == AskStatus.ABSTAINED.value
    assert final.data["abstention"]["reason"] == AbstentionReason.UNCITED.value
    assert llm is not None and len(llm.calls) == 2, "exactly one repair retry, then abstain"


def test_citation_outside_final_context_is_rejected() -> None:
    """A chunk_id from the WIDER fused candidates (not the final reranked
    context actually shown to the model) must fail Gate B — the model was
    never given that chunk to cite."""
    shown, hidden = _chunk("25.1"), _chunk("25.999")
    bad_json = (
        f'{{"answer_md": "An answer.", "citations": '
        f'[{{"chunk_id": "{hidden.id}", "claim": "x"}}], "insufficient": false}}'
    )
    svc, _, llm = _service(
        dense=[(shown, 0.9), (hidden, 0.1)],
        reranker_scores={shown.clause_path: 0.9, hidden.clause_path: 0.9},
        llm_responses=[bad_json, bad_json],
        context_k=1,  # only `shown` makes the final context
    )
    events = list(svc.ask("q?"))
    assert events[-1].data["abstention"]["reason"] == AbstentionReason.UNCITED.value
    assert llm is not None and len(llm.calls) == 2


def test_missing_citation_for_a_paragraph_triggers_gate_b_repair() -> None:
    c = _chunk("25.1")
    two_paragraphs_one_citation = (
        '{"answer_md": "First paragraph with a fact.\\n\\nSecond paragraph, uncited.", '
        f'"citations": [{{"chunk_id": "{c.id}", "claim": "x"}}], "insufficient": false}}'
    )
    svc, _, llm = _service(
        dense=[(c, 0.9)],
        reranker_scores={c.clause_path: 0.9},
        llm_responses=[two_paragraphs_one_citation, _valid_json(c, "One paragraph now.")],
    )
    events = list(svc.ask("q?"))
    assert events[-1].data["status"] == AskStatus.GROUNDED.value
    assert llm is not None and len(llm.calls) == 2, "paragraph/citation mismatch must repair"


# --- event ordering (spec §7 SSE contract) --------------------------------------


def test_event_order_for_grounded_answer() -> None:
    c = _chunk("25.1")
    svc, _, _ = _service(
        dense=[(c, 0.9)],
        reranker_scores={c.clause_path: 0.9},
        llm_responses=_valid_json(c),
    )
    events = list(svc.ask("q?"))
    types = [e.type for e in events]

    assert types[0] is AskEventType.STAGE
    assert types[1] is AskEventType.STAGE
    assert types[2] is AskEventType.STAGE
    assert events[0].data["stage"] == "retrieving"
    assert events[1].data["stage"] == "reranking"
    assert events[2].data["stage"] == "generating"
    assert all(t is AskEventType.TOKEN for t in types[3:-2])
    assert types[-2] is AskEventType.CITATIONS
    assert types[-1] is AskEventType.FINAL, "FINAL must be the last event"
    assert types.count(AskEventType.FINAL) == 1, "exactly one terminal event"
    assert AskEventType.ERROR not in types


def test_event_order_for_abstention_skips_generation_stage() -> None:
    c = _chunk("25.999")
    svc, _, _ = _service(
        dense=[(c, 0.9)],
        reranker_scores={c.clause_path: 0.05},
        llm_responses="unreachable",
    )
    events = list(svc.ask("q?"))
    types = [e.type for e in events]

    assert types == [
        AskEventType.STAGE,
        AskEventType.STAGE,
        AskEventType.CITATIONS,
        AskEventType.FINAL,
    ], "abstention must skip the 'generating' stage and TOKEN events entirely"
    assert types.count(AskEventType.FINAL) == 1


def test_error_event_terminates_on_unexpected_exception() -> None:
    """An unhandled exception anywhere in the pipeline becomes a single ERROR
    event, never an unhandled exception out of ask() (AD-2's generator contract)."""

    class _ExplodingLLM:
        model_name = "boom"

        def stream(self, system: str, user: str):  # type: ignore[no-untyped-def]
            raise ValueError("simulated provider failure")
            yield  # pragma: no cover - makes this a generator function

    c = _chunk("25.1")
    vec = FakeVectorIndex([(c, 0.9)])
    lex = FakeLexicalIndex([])
    rr = FakeReranker({c.clause_path: 0.9})
    svc = AskService(
        embedder=FakeEmbedder(),
        vector_index=vec,
        lexical_index=lex,
        reranker=rr,
        llm=_ExplodingLLM(),
        tau_retrieval=0.35,
    )
    events = list(svc.ask("q?"))
    assert events[-1].type is AskEventType.ERROR
    assert "simulated provider failure" in events[-1].data["message"]
    assert sum(1 for e in events if e.type in (AskEventType.FINAL, AskEventType.ERROR)) == 1


# --- cost accounting (AD-6) -----------------------------------------------------


def test_cost_is_null_without_a_price_entry() -> None:
    c = _chunk("25.1")
    svc, repo, _ = _service(
        dense=[(c, 0.9)],
        reranker_scores={c.clause_path: 0.9},
        llm_responses=_valid_json(c),
        model_prices=None,
    )
    list(svc.ask("q?"))
    saved = next(iter(repo.asks.values()))
    assert saved.cost_usd is None, "an unpriced model must never fake a cost"


def test_cost_is_computed_from_the_price_map() -> None:
    c = _chunk("25.1")
    svc, repo, _ = _service(
        dense=[(c, 0.9)],
        reranker_scores={c.clause_path: 0.9},
        llm_responses=_valid_json(c),
        llm_usages=TokenUsage(prompt_tokens=1_000_000, completion_tokens=1_000_000),
        model_prices={"fake-model": (0.59, 0.79)},
    )
    list(svc.ask("q?"))
    saved = next(iter(repo.asks.values()))
    assert saved.cost_usd == Decimal("1.38000")
