# Purpose: expose liveness and readiness probes for orchestrators and load balancers.
# Responsibilities: report process liveness cheaply and report dependency readiness (database and,
#   when configured, Redis) without leaking connection strings, secrets, or internal error detail.
# Dependencies: settings, the session factory, and the Redis health helper.
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.dependencies import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness: the process is up and serving. Does not touch dependencies."""
    return {"status": "ok"}


@router.get("/ready")
def ready(
    response: Response,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    """Readiness: report dependency + region state; 503 unless the service can safely serve.

    Ready requires the database, a working encryption provider, and — when signatures are enforced
    — mandatory Redis replay protection. Region role/epoch and maintenance mode are surfaced but do
    not themselves make the API unready (a standby still serves reads); side-effect workers gate.
    """
    from app.services.reliability.degraded import dependency_status, is_ready

    deps = dependency_status(session, settings)
    ok = is_ready(deps)
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if ok else "degraded",
        **deps,
        # Safe enforcement flags only — never secrets, signatures, or signing material.
        "monitor_signatures_enforced": settings.monitor_signature_required,
        "replay_backend": settings.replay_backend,
        "rate_limit_backend": settings.rate_limit_backend,
        "region": {
            "deployment_region": settings.deployment_region,
            "cluster_role": settings.cluster_role,
            "active_region_epoch": settings.active_region_epoch,
        },
    }
