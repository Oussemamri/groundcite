"""In-memory job registry for long-running writes (spec §9; AD-5).

DECIDED v1 trade, not a placeholder: single-tenant, so one process-wide
registry is correct and a queue (celery/rq/arq) is out of scope (spec §9
says "BackgroundTask in v1" verbatim). A process restart loses only a
job's STATUS -- the underlying work is durable in Postgres (the ingested
Document, the persisted eval_run) regardless, so nothing real is lost,
only the ability to poll a job that predates the restart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class JobKind(str, Enum):
    INGEST = "ingest"
    EVAL_RUN = "eval_run"


@dataclass
class Job:
    id: UUID
    kind: JobKind
    status: JobStatus = JobStatus.QUEUED
    detail: str | None = None
    result: dict[str, object] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class JobRegistry:
    """Process-wide job store, one instance on ``app.state.jobs`` (AD-5)."""

    def __init__(self) -> None:
        self._jobs: dict[UUID, Job] = {}

    def create(self, kind: JobKind) -> Job:
        job = Job(id=uuid4(), kind=kind)
        self._jobs[job.id] = job
        return job

    def get(self, job_id: UUID) -> Job | None:
        return self._jobs.get(job_id)

    def mark_running(self, job_id: UUID) -> None:
        job = self._jobs.get(job_id)
        if job is not None:
            job.status = JobStatus.RUNNING

    def mark_done(self, job_id: UUID, result: dict[str, object]) -> None:
        job = self._jobs.get(job_id)
        if job is not None:
            job.status = JobStatus.DONE
            job.result = result

    def mark_error(self, job_id: UUID, detail: str) -> None:
        job = self._jobs.get(job_id)
        if job is not None:
            job.status = JobStatus.ERROR
            job.detail = detail
