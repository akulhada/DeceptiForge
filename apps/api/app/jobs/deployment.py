# Purpose: worker entrypoint that drains the decoy-deployment queue.
# Responsibilities: run deployment execute/verify/retire/rollback jobs off the API path. A real
#   GitHub App adapter (installation tokens, git data API, webhooks) is not yet implemented; this
#   entrypoint refuses to run until one is wired, so it can never silently no-op in production.
# Run as: python -m app.jobs.deployment
from __future__ import annotations

from app.config.settings import get_settings
from app.jobs._runtime import log_event
from app.services.deployment.github_port import RepositoryDeploymentClient


def build_client() -> RepositoryDeploymentClient:
    """Return the configured repository-deployment client.

    The live GitHub App adapter is intentionally unimplemented in this milestone. Deployment logic
    is fully exercised in tests against the in-memory FakeDeploymentClient.
    """
    raise NotImplementedError(
        "no live repository-deployment adapter is configured; the GitHub App adapter "
        "(installation tokens + git data API + webhooks) is not implemented in this milestone"
    )


def run() -> int:
    settings = get_settings()
    if not settings.decoy_deployment_enabled:
        log_event("deployment_worker_disabled")
        return 0
    build_client()  # raises until a real adapter exists
    return 0


if __name__ == "__main__":
    run()
