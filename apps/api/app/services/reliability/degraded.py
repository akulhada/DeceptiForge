# Purpose: dependency + degraded-mode status for readiness and diagnostics.
# Responsibilities: report database, Redis (mandatory replay), encryption provider, active-region,
#   and maintenance state, and compute whether the service can safely perform its role. Never
#   reports ready when a mandatory protection is unavailable. No secrets. Dependencies: settings,
#   redis support, encryption, fencing.
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.services.encryption import secret_cipher
from app.services.redis_support import redis_health


def _database(session: Session) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return {"status": "unavailable"}
    return {"status": "ok"}


def _encryption(settings: Settings) -> dict[str, str]:
    # A round-trip proves the provider can decrypt what it encrypts (key access valid).
    try:
        cipher = secret_cipher(settings)
        if cipher.decrypt(cipher.encrypt("df-probe")) != "df-probe":
            return {"status": "unavailable"}
    except Exception:  # noqa: BLE001 - any provider error means encryption is not usable
        return {"status": "unavailable"}
    return {"status": "ok"}


def dependency_status(session: Session, settings: Settings) -> dict[str, object]:
    database = _database(session)
    redis = redis_health(settings)
    encryption = _encryption(settings)
    # Redis replay protection is mandatory when auth + signatures are enforced; missing it fails
    # closed for readiness (signed ingestion would otherwise be unsafe).
    replay_required = settings.auth_enabled and settings.monitor_signature_required
    replay_ok = redis["status"] in {"ok", "not_required"}
    return {
        "database": database,
        "redis": redis,
        "encryption": encryption,
        "replay_protection": {
            "required": replay_required,
            "status": "ok" if replay_ok else "unavailable",
        },
        "active_region": {
            "role": settings.cluster_role,
            "is_active_write_region": settings.is_active_write_region,
            "epoch": settings.active_region_epoch,
        },
        "maintenance_mode": settings.maintenance_mode,
    }


def is_ready(status: dict[str, object]) -> bool:
    """Ready only when the service can safely perform its role."""
    database = status["database"]
    encryption = status["encryption"]
    replay = status["replay_protection"]
    assert isinstance(database, dict) and isinstance(encryption, dict) and isinstance(replay, dict)
    if database["status"] != "ok" or encryption["status"] != "ok":
        return False
    if replay["required"] and replay["status"] != "ok":
        return False
    return True
