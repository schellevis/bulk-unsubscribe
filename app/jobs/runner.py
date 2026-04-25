import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db import get_session_factory
from app.models.job import Job, JobStatus, JobType


class JobContext:
    def __init__(self, job_id: int, session_factory) -> None:
        self.job_id = job_id
        self._session_factory = session_factory

    def set_total(self, total: int) -> None:
        with self._session_factory() as s:
            s.execute(
                update(Job).where(Job.id == self.job_id).values(progress_total=total)
            )
            s.commit()

    def advance(self, delta: int = 1) -> None:
        with self._session_factory() as s:
            job = s.get(Job, self.job_id)
            if job is None:
                return
            job.progress_done = job.progress_done + delta
            s.commit()


JobWork = Callable[[JobContext], Awaitable[dict | None]]


class JobRunner:
    def __init__(self, database_url: str | None = None) -> None:
        self._session_factory = get_session_factory(database_url)
        self._semaphore = asyncio.Semaphore(2)

    @staticmethod
    def create_job(
        session: Session,
        *,
        type: JobType,
        account_id: int | None,
        params: dict | None,
    ) -> int:
        job = Job(
            type=type,
            account_id=account_id,
            status=JobStatus.queued,
            params_json=json.dumps(params) if params is not None else None,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return job.id

    @staticmethod
    def recover_orphans(database_url: str | None = None) -> None:
        sf = get_session_factory(database_url)
        with sf() as s:
            s.execute(
                update(Job)
                .where(Job.status == JobStatus.running)
                .values(
                    status=JobStatus.failed,
                    error="interrupted by restart",
                    finished_at=datetime.now(timezone.utc),
                )
            )
            s.commit()

    async def run(self, job_id: int, work: JobWork) -> None:
        async with self._semaphore:
            with self._session_factory() as s:
                s.execute(
                    update(Job)
                    .where(Job.id == job_id)
                    .values(
                        status=JobStatus.running,
                        started_at=datetime.now(timezone.utc),
                    )
                )
                s.commit()

            ctx = JobContext(job_id, self._session_factory)
            try:
                result = await work(ctx)
            except Exception as exc:  # noqa: BLE001
                with self._session_factory() as s:
                    s.execute(
                        update(Job)
                        .where(Job.id == job_id)
                        .values(
                            status=JobStatus.failed,
                            error=str(exc),
                            finished_at=datetime.now(timezone.utc),
                        )
                    )
                    s.commit()
                return

            with self._session_factory() as s:
                s.execute(
                    update(Job)
                    .where(Job.id == job_id)
                    .values(
                        status=JobStatus.success,
                        result_json=json.dumps(result) if result is not None else None,
                        finished_at=datetime.now(timezone.utc),
                    )
                )
                s.commit()

    def schedule(self, job_id: int, work: JobWork) -> asyncio.Task:
        return asyncio.create_task(self.run(job_id, work))
