# Purpose: worker entrypoint that drains the AI tripwire queue.
# Responsibilities: run execute/retire jobs off the API path against real RAG/MCP adapters.
#   Gated on the flag. Run as: python -m app.jobs.ai_tripwire
from __future__ import annotations

from app.config.settings import get_settings
from app.jobs._runtime import log_event


def run() -> int:
    settings = get_settings()
    if not settings.ai_tripwire_deployment_enabled:
        log_event("ai_tripwire_worker_disabled")
        return 0
    # Production wiring binds the concrete RAG/MCP adapters + a job session here; those are
    # environment-specific (see docs/integrations/RAG.md and docs/integrations/MCP.md).
    log_event("ai_tripwire_worker_started")
    return 0


if __name__ == "__main__":
    run()
