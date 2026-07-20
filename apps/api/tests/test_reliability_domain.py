# Purpose: verify the failover state machine, recovery objectives, and cluster-role settings
#   validation.
from __future__ import annotations

import pytest

from app.config.settings import Settings
from app.models.domain.reliability import (
    RECOVERY_OBJECTIVES,
    DataClass,
    FailoverState,
    InvalidFailoverTransitionError,
    assert_transition,
    can_transition,
)


def test_secondary_never_promoted_before_primary_fenced() -> None:
    # The only path to promotion goes through PRIMARY_FENCED.
    assert not can_transition(FailoverState.FAILOVER_REQUESTED, FailoverState.STANDBY_PROMOTING)
    assert can_transition(FailoverState.FAILOVER_REQUESTED, FailoverState.PRIMARY_FENCED)
    assert can_transition(FailoverState.PRIMARY_FENCED, FailoverState.STANDBY_PROMOTING)


def test_full_failover_path() -> None:
    path = [
        FailoverState.NORMAL, FailoverState.FAILOVER_REQUESTED, FailoverState.PRIMARY_FENCED,
        FailoverState.STANDBY_PROMOTING, FailoverState.SECONDARY_ACTIVE,
        FailoverState.RECOVERY_VALIDATION, FailoverState.FAILBACK_PENDING,
        FailoverState.NORMAL_RESTORED, FailoverState.NORMAL,
    ]
    for a, b in zip(path, path[1:], strict=False):
        assert_transition(a, b)


def test_illegal_transition_rejected() -> None:
    with pytest.raises(InvalidFailoverTransitionError):
        assert_transition(FailoverState.NORMAL, FailoverState.SECONDARY_ACTIVE)


def test_recovery_objectives() -> None:
    assert RECOVERY_OBJECTIVES[DataClass.CRITICAL].rpo_minutes == 5
    assert RECOVERY_OBJECTIVES[DataClass.CRITICAL].rto_minutes == 60
    assert RECOVERY_OBJECTIVES[DataClass.DERIVED].recomputable is True


def _settings(**over) -> Settings:  # type: ignore[no-untyped-def]
    base = dict(
        database_url="postgresql+psycopg://u:p@localhost/db",  # type: ignore[arg-type]
        app_env="development",
    )
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


def test_ambiguous_cluster_role_rejected() -> None:
    with pytest.raises(ValueError, match="cluster_role"):
        _settings(cluster_role="both")
    assert _settings(cluster_role="standby").is_active_write_region is False
    assert _settings(cluster_role="primary").is_active_write_region is True


def test_dr_requires_secondary_region_in_prod() -> None:
    with pytest.raises(ValueError, match="secondary_region"):
        _settings(app_env="production", dr_enabled=True, secondary_region="")
