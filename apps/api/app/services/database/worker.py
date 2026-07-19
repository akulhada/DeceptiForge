# Purpose: drain the database-honey work queue, dispatching each job to the orchestration service.
# Responsibilities: claim jobs atomically, route by type, mark done/failed, never let one failing
#   job block the queue. Dependencies: repository, connector port, service, settings.
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.repositories.database_honey import DatabaseHoneyRepository
from app.services.database.connector_port import DatabaseConnectorClient
from app.services.database.service import DatabaseHoneyService


class DatabaseHoneyWorker:
    def __init__(
        self,
        session: Session,
        client: DatabaseConnectorClient,
        settings: Settings,
        *,
        batch: int = 20,
    ) -> None:
        self._repo = DatabaseHoneyRepository(session, settings)
        self._service = DatabaseHoneyService(self._repo, client, settings)
        self._batch = batch

    def run_once(self) -> int:
        jobs = self._repo.claim_jobs(self._batch)
        for job in jobs:
            try:
                self._dispatch(job.job_type, job.organization_id, job.deployment_id)
                self._repo.complete_job(job.id, ok=True)
            except Exception:  # noqa: BLE001 - a failed job is marked, never blocks the queue
                self._repo.complete_job(job.id, ok=False)
        return len(jobs)

    def _dispatch(self, job_type: str, organization_id, deployment_id) -> None:  # type: ignore[no-untyped-def]
        if job_type == "execute":
            self._service.execute(organization_id, deployment_id)
        elif job_type == "retire":
            self._service.retire(organization_id, deployment_id)
        elif job_type == "rollback":
            self._service.rollback(organization_id, deployment_id)
