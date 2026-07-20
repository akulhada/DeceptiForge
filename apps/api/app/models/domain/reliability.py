# Purpose: domain contract for multi-region reliability, backup/restore, and disaster recovery.
# Responsibilities: define cluster roles, the failover control-plane state machine, data classes +
#   recovery objectives, restore-verification check results, and runtime identity. No infrastructure
#   calls here. GPT is irrelevant to recovery. Dependencies: DomainModel base.
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.models.domain.base import DomainModel


class ClusterRole(StrEnum):
    PRIMARY = "primary"
    STANDBY = "standby"
    RECOVERY = "recovery"


class FailoverState(StrEnum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    FAILOVER_REQUESTED = "failover_requested"
    PRIMARY_FENCED = "primary_fenced"
    STANDBY_PROMOTING = "standby_promoting"
    SECONDARY_ACTIVE = "secondary_active"
    RECOVERY_VALIDATION = "recovery_validation"
    FAILBACK_PENDING = "failback_pending"
    NORMAL_RESTORED = "normal_restored"


# Closed failover state machine. A secondary is never promoted while the primary may still write
# (STANDBY_PROMOTING requires passing through PRIMARY_FENCED first).
_TRANSITIONS: dict[FailoverState, frozenset[FailoverState]] = {
    FailoverState.NORMAL: frozenset({FailoverState.DEGRADED, FailoverState.FAILOVER_REQUESTED}),
    FailoverState.DEGRADED: frozenset(
        {FailoverState.NORMAL, FailoverState.FAILOVER_REQUESTED}
    ),
    FailoverState.FAILOVER_REQUESTED: frozenset(
        {FailoverState.PRIMARY_FENCED, FailoverState.NORMAL}
    ),
    FailoverState.PRIMARY_FENCED: frozenset({FailoverState.STANDBY_PROMOTING}),
    FailoverState.STANDBY_PROMOTING: frozenset({FailoverState.SECONDARY_ACTIVE}),
    FailoverState.SECONDARY_ACTIVE: frozenset({FailoverState.RECOVERY_VALIDATION}),
    FailoverState.RECOVERY_VALIDATION: frozenset(
        {FailoverState.FAILBACK_PENDING, FailoverState.SECONDARY_ACTIVE}
    ),
    FailoverState.FAILBACK_PENDING: frozenset({FailoverState.NORMAL_RESTORED}),
    FailoverState.NORMAL_RESTORED: frozenset({FailoverState.NORMAL}),
}


class InvalidFailoverTransitionError(Exception):
    def __init__(self, current: FailoverState, target: FailoverState) -> None:
        super().__init__(f"illegal failover transition {current.value} -> {target.value}")
        self.current = current
        self.target = target


def can_transition(current: FailoverState, target: FailoverState) -> bool:
    return target in _TRANSITIONS.get(current, frozenset())


def assert_transition(current: FailoverState, target: FailoverState) -> None:
    if not can_transition(current, target):
        raise InvalidFailoverTransitionError(current, target)


class DataClass(StrEnum):
    CRITICAL = "critical"
    DERIVED = "derived"
    EPHEMERAL = "ephemeral"


class RecoveryObjective(DomainModel):
    data_class: DataClass
    rpo_minutes: int
    rto_minutes: int
    recomputable: bool = False


# Documented, tested targets by data class (actual achievable values recorded per drill).
RECOVERY_OBJECTIVES: dict[DataClass, RecoveryObjective] = {
    DataClass.CRITICAL: RecoveryObjective(
        data_class=DataClass.CRITICAL, rpo_minutes=5, rto_minutes=60
    ),
    DataClass.DERIVED: RecoveryObjective(
        data_class=DataClass.DERIVED, rpo_minutes=24 * 60, rto_minutes=4 * 60, recomputable=True
    ),
    DataClass.EPHEMERAL: RecoveryObjective(
        data_class=DataClass.EPHEMERAL, rpo_minutes=0, rto_minutes=0, recomputable=True
    ),
}


class RestoreCheck(DomainModel):
    """One deterministic restore-integrity check result."""

    name: str = Field(max_length=64)
    passed: bool
    detail: str = Field(default="", max_length=256)


class RestoreReport(DomainModel):
    """A signed/checksummed restore-verification report. Contains no secrets or raw evidence."""

    drill_id: str
    backup_identifier: str = Field(max_length=128)
    recovery_point: datetime
    started_at: datetime
    finished_at: datetime
    achieved_rpo_minutes: float
    achieved_rto_minutes: float
    migration_revision: str = Field(max_length=64)
    checks: tuple[RestoreCheck, ...]
    passed: bool
    checksum: str = Field(max_length=64)


class RuntimeIdentity(DomainModel):
    """Safe runtime identity exposed through internal diagnostics. No infrastructure credentials."""

    deployment_region: str = Field(max_length=64)
    cluster_id: str = Field(max_length=64)
    environment: str = Field(max_length=32)
    role: ClusterRole
    deployment_revision: str = Field(max_length=64)
    database_cluster_id: str = Field(max_length=64)
    active_region_epoch: int = Field(ge=0)
    secondary_region: str | None = Field(default=None, max_length=64)
    dr_enabled: bool = False
    maintenance_mode: bool = False
