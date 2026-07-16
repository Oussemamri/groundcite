"""EvalService — the differentiator; build before the UI (spec §8).

Week 2 (spec §15.1 amendment) implements the RETRIEVAL half: recall@5, recall@10
and MRR over the committed golden set, with NO judge, NO LLM and no Ragas. This
is the cheap, deterministic half of §8 — and the half §8 itself calls "the most
stable CI signal". It scores ``AskService.retrieve`` directly, which is why that
method takes no LLM port.

Week 3 Phase 5 adds the full-pipeline half: ``run_full`` drives ``AskService.ask``
through Gates A/B for every Case and hand-rolls citation_precision + abstention
correctness (spec §8 build-vs-buy: "~15 lines each"). ``faithfulness`` (ragas,
AD-7) is the ONLY judge-dependent column and stays NULL without ``--judge`` and a
second provider — retrieval + citation metrics never depend on a judge.

``run_full`` also computes recall@5/10/MRR per case via a companion
``retrieve()`` call (same shape as ``run_retrieval``): ``ask()`` does not expose
its internal retrieval result on the AskEvent stream (only what got cited, or
the abstention's top_passages), so the persisted ``eval_results`` row — one row
per (run, case) holding EVERY metric column (spec §5) — needs its own retrieval
pass for the recall columns. This duplicates one cheap, LLM-free retrieve() call
per case; changing ask()'s public contract to avoid it was judged not worth
destabilizing Phase 4's freshly-tested Gates A/B mid-Phase-5 (rule 0: boring).

Depends only on domain + ports + sibling services (never adapters/config): the
suite loader is injected as a callable, exactly as ``count_tokens`` is injected
into the Chunker (spec §6.1 #4).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from uuid import UUID, uuid4

from groundcite.domain.entities import EvalCase
from groundcite.domain.results import (
    AbstentionReason,
    AskEventType,
    AskStatus,
    EvalResult,
    EvalRun,
    FullEvalCaseResult,
    FullEvalReport,
    RetrievalCaseResult,
    RetrievalEvalReport,
)
from groundcite.ports.protocols import Repository
from groundcite.services.ask import AskService
from groundcite.services.metrics import (
    abstention_is_correct,
    citation_precision,
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
        repository: Repository | None = None,
    ) -> None:
        self._ask = ask
        self._load_suite = load_suite
        # None ⇒ run_full still scores and returns a report, just skips
        # persistence (mirrors AskService's optional repository, AD-6).
        self._repository = repository

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

    def run_full(
        self,
        suite: str,
        git_sha: str = "unknown",
        document_slugs: Sequence[str] | None = None,
        config: dict[str, object] | None = None,
        judge: bool = False,
    ) -> tuple[FullEvalReport, UUID]:
        """Score ``suite`` through the FULL pipeline — Gates A/B (spec §8 Phase 5).

        Persists one ``eval_runs`` row + one ``eval_results`` row per case (AD-6)
        when a repository is wired. Returns the report and the run id (for
        ``groundcite eval report <run-id>``) regardless of persistence.

        ``judge`` is accepted for the CLI's ``--judge`` flag but not yet wired to
        ragas (AD-7): no second LLM provider is configured this week, so
        ``mean_faithfulness`` and every case's ``faithfulness`` stay None either
        way — the run still completes, per spec §8 ("retrieval + citation metrics
        must never depend on a judge").
        """
        cases = list(self._load_suite(suite))
        run_id = uuid4()
        case_results: list[FullEvalCaseResult] = []
        eval_rows: list[EvalResult] = []

        for case in cases:
            status: AskStatus
            reason: AbstentionReason | None = None
            cited: list[str] = []
            cprec: float | None = None
            latency: int | None = None
            ask_id: UUID | None = None
            top_score: float | None = None
            error_message: str | None = None
            r5: float | None = None
            r10: float | None = None
            rr: float | None = None

            try:
                # Cheap, LLM-free retrieval pass for the persisted recall/MRR
                # columns (see module docstring — ask() does not expose this
                # itself).
                retrieval = self._ask.retrieve(
                    case.question, document_slugs=document_slugs, top_k=_EVAL_TOP_K
                )
                paths = [c.clause_path for c in retrieval.chunks]
                r5 = recall_at_k(paths, case.expected_clauses, 5)
                r10 = recall_at_k(paths, case.expected_clauses, 10)
                rr = reciprocal_rank(paths, case.expected_clauses)

                events = list(self._ask.ask(case.question, document_slugs=document_slugs))
                terminal = next(
                    (
                        e
                        for e in reversed(events)
                        if e.type in (AskEventType.FINAL, AskEventType.ERROR)
                    ),
                    None,
                )

                if terminal is None or terminal.type is AskEventType.ERROR:
                    status = AskStatus.ERROR
                    if terminal is None:
                        error_message = "no terminal event (stream ended without FINAL or ERROR)"
                    else:
                        error_message = str(terminal.data.get("message", ""))
                else:
                    status = AskStatus(str(terminal.data["status"]))
                    latency_raw = terminal.data.get("latency_ms")
                    latency = int(latency_raw) if isinstance(latency_raw, int | float) else None
                    ask_id_raw = terminal.data.get("ask_id")
                    ask_id = UUID(str(ask_id_raw)) if ask_id_raw else None
                    if status is AskStatus.GROUNDED:
                        answer = terminal.data["answer"]
                        assert isinstance(answer, dict)
                        cited = [
                            str(c["clause_path"])
                            for c in answer["citations"]
                            if isinstance(c, dict) and c.get("clause_path")
                        ]
                        cprec = citation_precision(cited, case.expected_clauses)
                        conf = answer.get("confidence")
                        top_score = float(conf) if isinstance(conf, int | float) else None
                    else:  # ABSTAINED
                        abstention = terminal.data["abstention"]
                        assert isinstance(abstention, dict)
                        reason = AbstentionReason(abstention["reason"])
                        conf = abstention.get("confidence")
                        top_score = float(conf) if isinstance(conf, int | float) else None
            except Exception as exc:
                # A case-level infrastructure failure (e.g. a transient
                # model-hub timeout during tokenizer load, hit live during
                # Phase 6) must not abort the whole suite -- every other case
                # still deserves a real result. recall/MRR stay None (never
                # faked, AD-6) rather than a misleading 0.0; the message is
                # captured the same way as the ask()-internal ERROR path so
                # this is diagnosable identically either way.
                status = AskStatus.ERROR
                error_message = f"{type(exc).__name__}: {exc}"

            grounded = status is AskStatus.GROUNDED
            correct = abstention_is_correct(case.must_abstain, grounded)

            case_results.append(
                FullEvalCaseResult(
                    case_id=case.id,
                    question=case.question,
                    language=case.language,
                    must_abstain=case.must_abstain,
                    status=status,
                    abstention_reason=reason,
                    abstention_correct=correct,
                    citation_precision=cprec,
                    cited_clauses=tuple(cited),
                    latency_ms=latency,
                    ask_id=ask_id,
                    top_score=top_score,
                    error_message=error_message,
                )
            )
            eval_rows.append(
                EvalResult(
                    run_id=run_id,
                    case_id=case.id,
                    recall_at_5=r5,
                    recall_at_10=r10,
                    mrr=rr,
                    citation_precision=cprec,
                    faithfulness=None,
                    abstained=(status is AskStatus.ABSTAINED),
                    passed=correct,
                    debug={
                        "top_score": top_score,
                        "status": status.value,
                        "cited_clauses": cited,
                        "latency_ms": latency,
                        "ask_id": str(ask_id) if ask_id else None,
                        "error_message": error_message,
                    },
                )
            )

        grounded_n = sum(1 for c in case_results if c.status is AskStatus.GROUNDED)
        abstained_n = sum(1 for c in case_results if c.status is AskStatus.ABSTAINED)
        error_n = sum(1 for c in case_results if c.status is AskStatus.ERROR)
        precisions = [
            c.citation_precision for c in case_results if c.citation_precision is not None
        ]

        report = FullEvalReport(
            suite=suite,
            git_sha=git_sha,
            judge=judge,
            total_cases=len(case_results),
            grounded_cases=grounded_n,
            abstained_cases=abstained_n,
            error_cases=error_n,
            abstention_accuracy=mean([1.0 if c.abstention_correct else 0.0 for c in case_results]),
            mean_citation_precision=mean(precisions),
            mean_faithfulness=None,
            cases=tuple(case_results),
            config=config or {},
        )

        if self._repository is not None:
            self._repository.save_eval_run(
                EvalRun(id=run_id, git_sha=git_sha, config=config or {}),
                cases,
                eval_rows,
            )
        return report, run_id

    def get_report(self, run_id: UUID) -> tuple[EvalRun, list[EvalResult]] | None:
        """Look up a past Run + its per-Case results (``groundcite eval report
        <run-id>``). None when no repository is wired or the run is unknown."""
        if self._repository is None:
            return None
        run = self._repository.get_eval_run(run_id)
        if run is None:
            return None
        return run, self._repository.get_eval_results(run_id)

    def list_runs(self) -> list[EvalRun]:
        """All eval Runs, newest first (Week 4: ``GET /eval/runs``). Thin
        Repository delegate so the API owns no adapter reference (§4 dependency
        rule). Empty when no repository is wired."""
        if self._repository is None:
            return []
        return self._repository.list_eval_runs()

    def get_cases(self, case_ids: Sequence[UUID]) -> dict[UUID, EvalCase]:
        """Case metadata for a set of case ids (Week 5 AD-2: `/evals` per-case
        drill-down). Thin Repository delegate, same shape as ``list_runs``.
        Empty when no repository is wired."""
        if self._repository is None:
            return {}
        return self._repository.get_eval_cases(case_ids)
