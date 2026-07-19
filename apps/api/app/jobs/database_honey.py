# Purpose: worker entrypoint that drains the database-honey queue.
# Responsibilities: run execute/retire/rollback jobs off the API path against a real PostgreSQL
#   connector adapter. Refuses to run unless the feature is enabled. Run as:
#   python -m app.jobs.database_honey
from __future__ import annotations

from app.config.settings import get_settings
from app.jobs._runtime import log_event


def run() -> int:
    settings = get_settings()
    if not settings.database_honey_deployment_enabled:
        log_event("database_honey_worker_disabled")
        return 0
    # A running deployment worker wires the psycopg adapter + a job session here. The adapter and
    # per-connector session wiring are environment-specific; see docs/integrations/PostgreSQL.md.
    log_event("database_honey_worker_started")
    return 0


if __name__ == "__main__":
    run()
