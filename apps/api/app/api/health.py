# Purpose: expose liveness and readiness probes for orchestrators and load balancers.
# Responsibilities: report process liveness cheaply and report dependency readiness (database and,
#   when configured, Redis) without leaking connection strings, secrets, or internal error detail.
# Dependencies: settings, the session factory, and the Redis health helper.
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.dependencies import get_db
from app.services.redis_support import redis_health

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
    """Readiness: report database and Redis dependency state; 503 if any required one is down."""
    database = _database_health(session)
    redis = redis_health(settings)
    ok = database["status"] == "ok" and redis["status"] in {"ok", "not_required"}
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if ok else "degraded", "database": database, "redis": redis}


def _database_health(session: Session) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return {"status": "unavailable"}
    return {"status": "ok"}
