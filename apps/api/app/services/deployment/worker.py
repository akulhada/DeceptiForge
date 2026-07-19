# Purpose: drain the deployment work queue, dispatching each job to the orchestration service.
# Responsibilities: claim jobs atomically (no duplicate processing), route by job type, mark the
#   job done/failed, and never let one failing job block the queue. Dependencies: repositories, the
#   client port, and DeploymentService.
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.repositories.artifacts import ArtifactRepository
from app.repositories.deployments import DeploymentRepository
from app.services.deployment.github_port import RepositoryDeploymentClient
from app.services.deployment.service import DeploymentService


class DeploymentWorker:
    def __init__(
        self,
        session: Session,
        client: RepositoryDeploymentClient,
        settings: Settings,
        *,
        batch: int = 20,
    ) -> None:
        self._session = session
        self._d = DeploymentRepository(session)
        self._service = DeploymentService(
            self._d, ArtifactRepository(session), client, settings
        )
        self._batch = batch

    def run_once(self) -> int:
        jobs = self._d.claim_jobs(self._batch)
        for job in jobs:
            try:
                self._dispatch(job.job_type, job.organization_id, job.deployment_id)
                self._d.complete_job(job.id, ok=True)
            except Exception:  # noqa: BLE001 - a failed job is marked, never blocks the queue
                self._d.complete_job(job.id, ok=False)
        return len(jobs)

    def _dispatch(self, job_type: str, organization_id, deployment_id) -> None:  # type: ignore[no-untyped-def]
        if job_type == "execute":
            self._service.execute(organization_id, deployment_id)
        elif job_type == "verify":
            self._service.verify(organization_id, deployment_id)
        elif job_type == "retire":
            self._service.retire(organization_id, deployment_id)
        elif job_type == "rollback":
            self._service.rollback(organization_id, deployment_id)
