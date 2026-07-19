# Purpose: domain contract for decoy deployment approval + lifecycle management.
# Responsibilities: define the deployment/item/approval/audit statuses and the explicit state
#   machine (allowed transitions), plus immutable domain models for previews and change-sets. No
#   GitHub or persistence concerns live here. Dependencies: the DomainModel base only.
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from app.models.domain.base import DomainModel


class DeploymentStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_APPROVAL = "awaiting_approval"
    PREVIEW_STALE = "preview_stale"
    REAPPROVAL_REQUIRED = "reapproval_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    DEPLOYED_UNMONITORED = "deployed_unmonitored"
    VERIFICATION_FAILED = "verification_failed"
    FAILED_ACTIVATION = "failed_activation"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETIRING = "retiring"
    RETIRED = "retired"
    ROLLBACK_PENDING = "rollback_pending"
    ROLLED_BACK = "rolled_back"
    EXPIRED = "expired"


class DeploymentOperation(StrEnum):
    CREATE = "create"
    APPEND = "append"
    MODIFY = "modify"


class ItemStatus(StrEnum):
    PLANNED = "planned"
    DEPLOYED = "deployed"
    VERIFIED = "verified"
    RETIRED = "retired"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


# Explicit, closed state machine. A transition not listed here is rejected. States that are terminal
# have no outgoing edges. Deployment before validation acceptance is blocked in the service layer,
# not encoded here.
_TRANSITIONS: dict[DeploymentStatus, frozenset[DeploymentStatus]] = {
    DeploymentStatus.DRAFT: frozenset(
        {DeploymentStatus.AWAITING_APPROVAL, DeploymentStatus.CANCELLED}
    ),
    DeploymentStatus.AWAITING_APPROVAL: frozenset(
        {
            DeploymentStatus.APPROVED,
            DeploymentStatus.REJECTED,
            DeploymentStatus.PREVIEW_STALE,
            DeploymentStatus.CANCELLED,
        }
    ),
    DeploymentStatus.PREVIEW_STALE: frozenset({DeploymentStatus.REAPPROVAL_REQUIRED}),
    DeploymentStatus.REAPPROVAL_REQUIRED: frozenset(
        {DeploymentStatus.AWAITING_APPROVAL, DeploymentStatus.CANCELLED}
    ),
    DeploymentStatus.APPROVED: frozenset(
        {DeploymentStatus.DEPLOYING, DeploymentStatus.PREVIEW_STALE, DeploymentStatus.CANCELLED}
    ),
    DeploymentStatus.DEPLOYING: frozenset(
        {
            DeploymentStatus.DEPLOYED,
            DeploymentStatus.DEPLOYED_UNMONITORED,
            DeploymentStatus.VERIFICATION_FAILED,
            DeploymentStatus.FAILED_ACTIVATION,
            DeploymentStatus.FAILED,
            DeploymentStatus.CANCELLED,
        }
    ),
    DeploymentStatus.DEPLOYED: frozenset(
        {
            DeploymentStatus.RETIRING,
            DeploymentStatus.ROLLBACK_PENDING,
            DeploymentStatus.EXPIRED,
        }
    ),
    DeploymentStatus.DEPLOYED_UNMONITORED: frozenset(
        {
            DeploymentStatus.RETIRING,
            DeploymentStatus.ROLLBACK_PENDING,
            DeploymentStatus.EXPIRED,
        }
    ),
    DeploymentStatus.VERIFICATION_FAILED: frozenset(
        {DeploymentStatus.ROLLBACK_PENDING, DeploymentStatus.RETIRING}
    ),
    DeploymentStatus.FAILED_ACTIVATION: frozenset(
        {DeploymentStatus.ROLLBACK_PENDING, DeploymentStatus.RETIRING}
    ),
    # A failed deployment re-enters only through re-approval, never straight to deployed.
    DeploymentStatus.FAILED: frozenset(
        {DeploymentStatus.AWAITING_APPROVAL, DeploymentStatus.CANCELLED}
    ),
    DeploymentStatus.RETIRING: frozenset({DeploymentStatus.RETIRED, DeploymentStatus.FAILED}),
    DeploymentStatus.ROLLBACK_PENDING: frozenset(
        {DeploymentStatus.ROLLED_BACK, DeploymentStatus.FAILED}
    ),
    DeploymentStatus.EXPIRED: frozenset({DeploymentStatus.RETIRING}),
    # Terminal states.
    DeploymentStatus.REJECTED: frozenset(),
    DeploymentStatus.CANCELLED: frozenset(),
    DeploymentStatus.RETIRED: frozenset(),
    DeploymentStatus.ROLLED_BACK: frozenset(),
}

# States from which monitoring may be active (used to enforce "no active registry after retire").
ACTIVE_MONITORING_STATES: frozenset[DeploymentStatus] = frozenset({DeploymentStatus.DEPLOYED})


class InvalidTransitionError(Exception):
    """Raised when a deployment status transition is not permitted by the state machine."""

    def __init__(self, current: DeploymentStatus, target: DeploymentStatus) -> None:
        super().__init__(f"invalid deployment transition: {current.value} -> {target.value}")
        self.current = current
        self.target = target


def can_transition(current: DeploymentStatus, target: DeploymentStatus) -> bool:
    return target in _TRANSITIONS.get(current, frozenset())


def assert_transition(current: DeploymentStatus, target: DeploymentStatus) -> None:
    if not can_transition(current, target):
        raise InvalidTransitionError(current, target)


# ---- preview / change-set domain models ----------------------------------------------------------


class ChangeSetItem(DomainModel):
    """One planned file change in a preview (content is rendered inert, never a real secret)."""

    decoy_id: UUID
    decoy_type: str
    target_path: str = Field(min_length=1, max_length=2048)
    operation: DeploymentOperation
    trace_identifier: str = Field(min_length=1, max_length=128)
    original_content_hash: str | None = None
    proposed_content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    unified_diff: str = Field(max_length=200_000)
    warnings: tuple[str, ...] = ()


class DeploymentPreview(DomainModel):
    """The exact, deterministic change set generated before any write."""

    deployment_id: UUID
    repository_id: UUID
    target_branch: str
    base_branch: str
    base_commit_sha: str
    items: tuple[ChangeSetItem, ...]
    decoy_types: tuple[str, ...]
    trace_identifiers: tuple[str, ...]
    validation_decision: str
    collision_ok: bool
    expected_monitoring_registration: tuple[str, ...]
    expires_at: datetime | None
    rollback_strategy: str
    warnings: tuple[str, ...] = ()
    changed_files: int
    changed_bytes: int
    blast_radius: str
    preview_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
