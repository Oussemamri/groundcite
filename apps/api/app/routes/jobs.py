"""Read route: job status (spec §9; AD-5).

``POST /documents`` and ``POST /eval/runs`` return ``{"job_id": ...}``; this
is how a client polls the outcome. 404 for an unknown id -> RFC-7807 (AD-6).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.deps import get_jobs
from app.errors import NotFoundError
from app.jobs import JobRegistry
from app.models import JobOut

router = APIRouter(prefix="/api/v1", tags=["jobs"])


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, jobs: JobRegistry = Depends(get_jobs)) -> JobOut:
    try:
        jid = UUID(job_id)
    except ValueError as exc:
        raise NotFoundError(slug=job_id, label="job") from exc
    job = jobs.get(jid)
    if job is None:
        raise NotFoundError(slug=job_id, label="job")
    return JobOut.from_job(job)
