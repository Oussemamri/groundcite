"""EvalService — the differentiator; build before the UI (spec §8).

Week 2 (spec §15.1 amendment) implements the RETRIEVAL half: recall@5, recall@10
and MRR over the committed golden set, with NO judge, NO LLM and no Ragas. This
is the cheap, deterministic half of §8 — and the half §8 itself calls "the most
stable CI signal". It scores ``AskService.retrieve`` directly, which is why that
method takes no LLM port.

Week 3 adds the judge half on top (citation_precision, faithfulness via Ragas,
abstention correctness at Gate A) plus eval_runs/eval_results persistence.

Depends only on domain + ports + sibling services (never adapters/config): the
suite loader is injected as a callable, exactly as ``count_tokens`` is injected
into the Chunker (spec §6.1 #4).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from groundcite.domain.entities import EvalCase
from groundcite.domain.results import (
    RetrievalCaseResult,
    RetrievalEvalReport,
)
from groundcite.services.ask import AskService
from groundcite.services.metrics import (
    first_hit_rank,
    mean,
    recall_at_k,
    reciprocal_rank,
)

# recall@10 is the widest metric we report, so every case retrieves at least 10.
_EVAL_TOP_K = 10


class EvalService:
    """Run eval Suites and score each Case (spec §8)."""

    def __init__(
        self,
        ask: AskService,
        load_suite: Callable[[str], Sequence[EvalCase]],
    ) -> None:
        self._ask = ask
        self._load_suite = load_suite

    def run_retrieval(
        self,
        suite: str,
        git_sha: str = "unknown",
        document_slugs: Sequence[str] | None = None,
        config: dict[str, object] | None = None,
    ) -> RetrievalEvalReport:
        """Score ``suite`` on retrieval only (spec §8 recall@k / MRR, §15.1)."""
        cases = list(self._load_suite(suite))
        results: list[RetrievalCaseResult] = []
        reranked = False

        for case in cases:
            retrieval = self._ask.retrieve(
                case.question,
                document_slugs=document_slugs,
                top_k=_EVAL_TOP_K,
            )
            reranked = retrieval.reranked
            paths = [c.clause_path for c in retrieval.chunks]
            results.append(
                RetrievalCaseResult(
                    case_id=case.id,
                    question=case.question,
                    language=case.language,
                    must_abstain=case.must_abstain,
                    expected_clauses=case.expected_clauses,
                    retrieved_clauses=tuple(paths),
                    recall_at_5=recall_at_k(paths, case.expected_clauses, 5),
                    recall_at_10=recall_at_k(paths, case.expected_clauses, 10),
                    reciprocal_rank=reciprocal_rank(paths, case.expected_clauses),
                    first_hit_rank=first_hit_rank(paths, case.expected_clauses),
                    top_score=retrieval.chunks[0].score if retrieval.chunks else None,
                )
            )

        # Means over SCORABLE cases only — a must-abstain case has no expected
        # clause, so folding its 0.0 into recall would silently depress the
        # number and misreport the retriever (abstention is Gate A, Week 3).
        scorable = [r for r in results if not r.must_abstain and r.expected_clauses]
        return RetrievalEvalReport(
            suite=suite,
            git_sha=git_sha,
            reranked=reranked,
            scored_cases=len(scorable),
            must_abstain_cases=sum(1 for r in results if r.must_abstain),
            recall_at_5=mean([r.recall_at_5 for r in scorable]),
            recall_at_10=mean([r.recall_at_10 for r in scorable]),
            mrr=mean([r.reciprocal_rank for r in scorable]),
            cases=tuple(results),
            config=config or {},
        )
