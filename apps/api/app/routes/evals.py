"""Eval run routes (spec §9).

- ``GET /api/v1/eval/runs`` — list eval Runs, newest first.
- ``GET /api/v1/eval/runs/{id}`` — one Run + its per-Case results (spec §8
  report shape).
- ``POST /api/v1/eval/runs`` — body ``{suite, full}`` -> ``{job_id}`` (AD-5).
  Mirrors ``groundcite eval run``'s config snapshot exactly, so a run
  triggered via the API is indistinguishable in ``eval_runs.config`` from
  one triggered via the CLI.

Routes are thin (parse → service → serialize). 404 for unknown id → RFC-7807
(AD-6).
"""

from __future__ import annotations

import subprocess
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, ConfigDict

from app.deps import get_app_settings, get_jobs, get_services
from app.errors import NotFoundError
from app.jobs import JobKind, JobRegistry
from app.logging_conf import get_logger
from app.models import EvalResultOut, EvalRunAggregatesOut, EvalRunDetailOut, EvalRunOut, JobOut
from groundcite.config import Settings
from groundcite.container import Services

router = APIRouter(prefix="/api/v1", tags=["evals"])


class EvalRunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite: str
    full: bool = False


@router.get("/eval/runs", response_model=list[EvalRunOut])
def list_eval_runs(services: Services = Depends(get_services)) -> list[EvalRunOut]:
    return [EvalRunOut.from_domain(r) for r in services.evals.list_runs()]


@router.get("/eval/runs/{run_id}", response_model=EvalRunDetailOut)
def get_eval_run(run_id: str, services: Services = Depends(get_services)) -> EvalRunDetailOut:
    try:
        rid = UUID(run_id)
    except ValueError as exc:
        raise NotFoundError(slug=run_id, label="eval run") from exc
    report = services.evals.get_report(rid)
    if report is None:
        raise NotFoundError(slug=run_id, label="eval run")
    run, results = report
    cases = services.evals.get_cases([r.case_id for r in results])
    return EvalRunDetailOut(
        run=EvalRunOut.from_domain(run),
        results=[EvalResultOut.from_domain(r, cases.get(r.case_id)) for r in results],
        aggregates=EvalRunAggregatesOut.from_results(results),
    )


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover
        return "unknown"


def _run_eval(
    services: Services, jobs: JobRegistry, job_id: UUID, body: EvalRunIn, settings: Settings
) -> None:
    log = get_logger("app.evals.run")
    jobs.mark_running(job_id)
    log.info("eval_run_started", job_id=str(job_id), suite=body.suite, full=body.full)
    git_sha = _git_sha()
    config_snapshot: dict[str, object] = {
        "embedding_model": settings.embedding_model,
        "reranker_enabled": settings.reranker_enabled,
        "reranker_model": settings.reranker_model if settings.reranker_enabled else None,
        "rrf_k": settings.rrf_k,
        "candidates_dense": settings.candidates_dense,
        "candidates_lexical": settings.candidates_lexical,
        "fused_k": settings.fused_k,
        "context_k": settings.context_k,
    }
    try:
        result: dict[str, object]
        if body.full:
            config_snapshot["tau_retrieval"] = settings.tau_retrieval
            config_snapshot["groq_model"] = settings.groq_model
            config_snapshot["llm_provider"] = settings.llm_provider
            config_snapshot["judge"] = False
            full_report, run_id = services.evals.run_full(
                body.suite, git_sha=git_sha, config=config_snapshot
            )
            result = {
                "run_id": str(run_id),
                "suite": body.suite,
                "full": True,
                "total_cases": full_report.total_cases,
                "grounded_cases": full_report.grounded_cases,
                "abstained_cases": full_report.abstained_cases,
            }
        else:
            retrieval_report = services.evals.run_retrieval(
                body.suite, git_sha=git_sha, config=config_snapshot
            )
            result = {
                "run_id": None,  # retrieval-only runs are not persisted (spec §15.1)
                "suite": body.suite,
                "full": False,
                "scored_cases": retrieval_report.scored_cases,
                "recall_at_5": retrieval_report.recall_at_5,
            }
        jobs.mark_done(job_id, result)
        log.info("eval_run_done", job_id=str(job_id))
    except Exception as exc:
        jobs.mark_error(job_id, str(exc))
        log.exception("eval_run_failed", job_id=str(job_id), error=str(exc))


@router.post("/eval/runs", response_model=JobOut, status_code=202)
def trigger_eval_run(
    body: EvalRunIn,
    background_tasks: BackgroundTasks,
    services: Services = Depends(get_services),
    jobs: JobRegistry = Depends(get_jobs),
    settings: Settings = Depends(get_app_settings),
) -> JobOut:
    job = jobs.create(JobKind.EVAL_RUN)
    background_tasks.add_task(_run_eval, services, jobs, job.id, body, settings)
    return JobOut.from_job(job)
