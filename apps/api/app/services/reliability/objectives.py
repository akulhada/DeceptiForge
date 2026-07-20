# Purpose: deterministic RPO/RTO computation for restore drills.
# Responsibilities: compute achieved RPO (data loss window = recovery point behind the last durable
#   write) and RTO (time to restore service) in minutes from timestamps. Deterministic; no I/O.
from __future__ import annotations

from datetime import UTC, datetime


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def achieved_rpo_minutes(last_durable_write: datetime, recovery_point: datetime) -> float:
    """RPO = how far the recovery point trails the last durable write, in minutes (>= 0)."""
    delta = (_aware(last_durable_write) - _aware(recovery_point)).total_seconds() / 60.0
    return round(max(0.0, delta), 3)


def achieved_rto_minutes(started_at: datetime, finished_at: datetime) -> float:
    """RTO = restore/validation wall-clock duration, in minutes (>= 0)."""
    delta = (_aware(finished_at) - _aware(started_at)).total_seconds() / 60.0
    return round(max(0.0, delta), 3)


def within_targets(
    *, rpo: float, rto: float, rpo_target: int, rto_target: int
) -> bool:
    return rpo <= rpo_target and rto <= rto_target
