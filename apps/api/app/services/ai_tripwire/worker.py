# Purpose: drain the AI tripwire work queue, dispatching each job to the orchestration service.
# Responsibilities: claim jobs atomically, route by type, mark done/failed, never block the queue.
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.repositories.ai_tripwire import AiTripwireRepository
from app.services.ai_tripwire.connectors import McpConnectorAdapter, RagConnectorAdapter
from app.services.ai_tripwire.service import AiTripwireService


class AiTripwireWorker:
    def __init__(
        self,
        session: Session,
        rag_client: RagConnectorAdapter,
        mcp_client: McpConnectorAdapter,
        settings: Settings,
        *,
        batch: int = 20,
    ) -> None:
        self._repo = AiTripwireRepository(session, settings)
        self._service = AiTripwireService(self._repo, rag_client, mcp_client, settings)
        self._batch = batch

    def run_once(self) -> int:
        jobs = self._repo.claim_jobs(self._batch)
        for job in jobs:
            try:
                if job.job_type == "execute":
                    self._service.execute(job.organization_id, job.deployment_id)
                elif job.job_type == "retire":
                    self._service.retire(job.organization_id, job.deployment_id)
                self._repo.complete_job(job.id, ok=True)
            except Exception:  # noqa: BLE001 - a failed job is marked, never blocks the queue
                self._repo.complete_job(job.id, ok=False)
        return len(jobs)
