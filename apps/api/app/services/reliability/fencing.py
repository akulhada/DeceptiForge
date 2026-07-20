# Purpose: region fencing + scheduler leadership gating to prevent split-brain.
# Responsibilities: decide whether this process may accept authoritative writes, run scheduled jobs,
#   or execute external side-effect work, based on cluster role, maintenance mode, feature gates,
#   and the active-region epoch. Stale-epoch callers are rejected. Deterministic; no infra calls.
#   Dependencies: settings, reliability domain.
from __future__ import annotations

from app.config.settings import Settings
from app.models.domain.reliability import ClusterRole, RuntimeIdentity


class RegionFencedError(Exception):
    """Raised when a write/side-effect/scheduler action is attempted on a non-active region or under
    maintenance. Message is safe."""


class StaleEpochError(Exception):
    """Raised when a caller presents an active-region epoch older than the current one."""


def runtime_identity(settings: Settings) -> RuntimeIdentity:
    return RuntimeIdentity(
        deployment_region=settings.deployment_region, cluster_id=settings.cluster_id,
        environment=settings.app_env, role=ClusterRole(settings.cluster_role),
        deployment_revision=settings.deployment_revision,
        database_cluster_id=settings.database_cluster_id,
        active_region_epoch=settings.active_region_epoch,
        secondary_region=settings.secondary_region or None, dr_enabled=settings.dr_enabled,
        maintenance_mode=settings.maintenance_mode,
    )


def is_active_write_region(settings: Settings) -> bool:
    return settings.is_active_write_region and not settings.maintenance_mode


def require_writes(settings: Settings) -> None:
    """Guard authoritative writes. A standby/recovery region or maintenance mode fails closed."""
    if settings.maintenance_mode:
        raise RegionFencedError("maintenance mode: writes are disabled")
    if not settings.is_active_write_region:
        raise RegionFencedError("this region is not the active write region")


def require_side_effects(settings: Settings) -> None:
    """Guard external side effects (repo/db/RAG/MCP deploys, SIEM delivery). Only the active write
    region with side effects enabled may run them, so a promoted-but-fenced region cannot duplicate
    external changes."""
    require_writes(settings)
    if not settings.external_side_effects_enabled:
        raise RegionFencedError("external side effects are disabled on this region")


def scheduler_allowed(settings: Settings) -> bool:
    """A scheduled job (retention, coverage, delivery retry, expiry) may only run on the active
    write region with schedulers enabled — never on two regions at once."""
    return (
        settings.schedulers_enabled
        and settings.is_active_write_region
        and not settings.maintenance_mode
    )


def check_epoch(settings: Settings, claimed_epoch: int) -> None:
    """Reject a side-effect request that carries a stale active-region epoch (fencing token)."""
    if claimed_epoch < settings.active_region_epoch:
        raise StaleEpochError(
            f"stale active-region epoch {claimed_epoch} < {settings.active_region_epoch}"
        )
