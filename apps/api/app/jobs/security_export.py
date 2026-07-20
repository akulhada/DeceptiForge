# Purpose: the security-export delivery worker entrypoint.
# Responsibilities: drain due integration deliveries off the ingestion path — build, send, record
#   each via the DeliveryWorker with the production HTTP transport. Gated on the flag. Bounded per
#   run. Run as: python -m app.jobs.security_export. Dependencies: worker, http transport, settings.
from __future__ import annotations

from app.config.settings import get_settings
from app.jobs._runtime import job_session, log_event
from app.services.integrations.http import build_http_transport
from app.services.integrations.worker import DeliveryWorker


def run() -> int:
    settings = get_settings()
    if not settings.security_integrations_enabled:
        log_event("security_export_worker_disabled")
        return 0
    with job_session() as session:
        delivered = DeliveryWorker(session, build_http_transport(), settings).run_once()
    log_event("security_export_worker_ran", processed=delivered)
    return delivered


if __name__ == "__main__":
    run()
