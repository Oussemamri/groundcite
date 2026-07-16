"""Read routes: eval runs (spec §9).

- ``GET /api/v1/eval/runs`` — list eval Runs, newest first.
- ``GET /api/v1/eval/runs/{id}`` — one Run + its per-Case results (spec §8
  report shape).

Routes are thin (parse → service → serialize). 404 for unknown id → RFC-7807
(AD-6). Trigger (``POST /eval/runs``) is a write route (Phase 4, jobs).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.deps import get_services
from app.errors import NotFoundError
from app.models import EvalResultOut, EvalRunDetailOut, EvalRunOut
from groundcite.container import Services

router = APIRouter(prefix="/api/v1", tags=["evals"])


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
    return EvalRunDetailOut(
        run=EvalRunOut.from_domain(run),
        results=[EvalResultOut.from_domain(r) for r in results],
    )
