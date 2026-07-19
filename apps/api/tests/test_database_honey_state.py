# Purpose: verify the database-honey deployment state machine and scope/role wiring.
from __future__ import annotations

import pytest

from app.models.domain.database_honey import (
    HoneyDeploymentStatus,
    InvalidHoneyTransitionError,
    assert_transition,
    can_transition,
)
from app.services.api_keys import ROLE_SCOPES

S = HoneyDeploymentStatus


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.DRAFT, S.AWAITING_APPROVAL),
        (S.AWAITING_APPROVAL, S.APPROVED),
        (S.AWAITING_APPROVAL, S.REJECTED),
        (S.APPROVED, S.DEPLOYING),
        (S.DEPLOYING, S.DEPLOYED),
        (S.DEPLOYING, S.FAILED),
        (S.DEPLOYED, S.RETIRING),
        (S.DEPLOYED, S.ROLLBACK_PENDING),
        (S.DEPLOYED, S.DRIFT_DETECTED),
        (S.RETIRING, S.RETIRED),
        (S.ROLLBACK_PENDING, S.ROLLED_BACK),
        (S.FAILED, S.AWAITING_APPROVAL),
        (S.DRIFT_DETECTED, S.RETIRING),
    ],
)
def test_allowed(current: HoneyDeploymentStatus, target: HoneyDeploymentStatus) -> None:
    assert can_transition(current, target)
    assert_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.REJECTED, S.DEPLOYING),
        (S.DRAFT, S.DEPLOYED),
        (S.RETIRED, S.DEPLOYING),
        (S.FAILED, S.DEPLOYED),
        (S.AWAITING_APPROVAL, S.DEPLOYING),
        (S.DEPLOYED, S.DEPLOYED),
    ],
)
def test_forbidden(current: HoneyDeploymentStatus, target: HoneyDeploymentStatus) -> None:
    assert not can_transition(current, target)
    with pytest.raises(InvalidHoneyTransitionError):
        assert_transition(current, target)


def test_terminal_states() -> None:
    for terminal in (S.REJECTED, S.CANCELLED, S.RETIRED, S.ROLLED_BACK):
        assert all(not can_transition(terminal, other) for other in HoneyDeploymentStatus)


def test_role_scopes() -> None:
    assert "database_honey:read" in ROLE_SCOPES["viewer"]
    assert "database_schema:read" in ROLE_SCOPES["viewer"]
    assert "database_honey:create" not in ROLE_SCOPES["viewer"]
    assert "database_honey:create" in ROLE_SCOPES["analyst"]
    assert "database_honey:approve" not in ROLE_SCOPES["analyst"]
    assert "database_honey:deploy" in ROLE_SCOPES["service"]
    assert "database_honey:approve" not in ROLE_SCOPES["service"]
    assert "database_honey:create" not in ROLE_SCOPES["service"]
    for scope in ("database_connectors:manage", "database_honey:approve", "database_honey:retire"):
        assert scope in ROLE_SCOPES["owner"] and scope in ROLE_SCOPES["admin"]
