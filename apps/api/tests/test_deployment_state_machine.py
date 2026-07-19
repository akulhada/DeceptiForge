# Purpose: verify the decoy-deployment state machine and scope/role wiring.
# Responsibilities: assert allowed transitions, reject forbidden ones (including the spec's explicit
#   forbidden edges), and confirm the new decoy_deployments scopes map to roles as intended.
from __future__ import annotations

import pytest

from app.models.domain.deployment import (
    DeploymentStatus,
    InvalidTransitionError,
    assert_transition,
    can_transition,
)
from app.services.api_keys import ROLE_SCOPES

S = DeploymentStatus


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.DRAFT, S.AWAITING_APPROVAL),
        (S.AWAITING_APPROVAL, S.APPROVED),
        (S.AWAITING_APPROVAL, S.REJECTED),
        (S.AWAITING_APPROVAL, S.PREVIEW_STALE),
        (S.PREVIEW_STALE, S.REAPPROVAL_REQUIRED),
        (S.REAPPROVAL_REQUIRED, S.AWAITING_APPROVAL),
        (S.APPROVED, S.DEPLOYING),
        (S.DEPLOYING, S.DEPLOYED),
        (S.DEPLOYING, S.DEPLOYED_UNMONITORED),
        (S.DEPLOYING, S.FAILED),
        (S.DEPLOYED, S.RETIRING),
        (S.DEPLOYED, S.ROLLBACK_PENDING),
        (S.RETIRING, S.RETIRED),
        (S.ROLLBACK_PENDING, S.ROLLED_BACK),
        (S.FAILED, S.AWAITING_APPROVAL),
    ],
)
def test_allowed_transitions(current: DeploymentStatus, target: DeploymentStatus) -> None:
    assert can_transition(current, target)
    assert_transition(current, target)  # does not raise


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.REJECTED, S.DEPLOYING),
        (S.DRAFT, S.DEPLOYED),
        (S.RETIRED, S.DEPLOYING),
        (S.FAILED, S.DEPLOYED),
        (S.AWAITING_APPROVAL, S.DEPLOYING),  # must be approved first
        (S.ROLLED_BACK, S.DEPLOYING),
        (S.DEPLOYED, S.DEPLOYED),  # no self-loop
    ],
)
def test_forbidden_transitions(current: DeploymentStatus, target: DeploymentStatus) -> None:
    assert not can_transition(current, target)
    with pytest.raises(InvalidTransitionError):
        assert_transition(current, target)


def test_terminal_states_have_no_exits() -> None:
    for terminal in (S.REJECTED, S.CANCELLED, S.RETIRED, S.ROLLED_BACK):
        assert all(not can_transition(terminal, other) for other in DeploymentStatus)


def test_role_scopes_for_deployments() -> None:
    assert "decoy_deployments:read" in ROLE_SCOPES["viewer"]
    assert "decoy_deployments:create" not in ROLE_SCOPES["viewer"]
    assert "decoy_deployments:create" in ROLE_SCOPES["analyst"]
    assert "decoy_deployments:approve" not in ROLE_SCOPES["analyst"]
    # Service keys may execute approved deployments but never create or approve them.
    assert "decoy_deployments:execute" in ROLE_SCOPES["service"]
    assert "decoy_deployments:approve" not in ROLE_SCOPES["service"]
    assert "decoy_deployments:create" not in ROLE_SCOPES["service"]
    for scope in (
        "decoy_deployments:approve",
        "decoy_deployments:execute",
        "decoy_deployments:retire",
        "decoy_deployments:rollback",
    ):
        assert scope in ROLE_SCOPES["owner"] and scope in ROLE_SCOPES["admin"]
