# Purpose: the reviewed lifecycle for calibration model versions.
# Responsibilities: enforce the permitted status transitions (never candidate->active, never
#   rejected->active), separation of duties between the requester and the approver, feature-schema
#   compatibility, cross-tenant activation refusal, and the safety-constraint precondition. Pure
#   logic so it is exhaustively testable. Dependencies: learning domain contracts. No I/O.
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.models.domain.learning import (
    FEATURE_SCHEMA_VERSION,
    ModelScope,
    ModelStatus,
    transition_allowed,
)


class VersionTransitionError(ValueError):
    """Raised when a lifecycle action is not permitted."""


@dataclass(frozen=True)
class VersionView:
    """The subset of a model version the lifecycle rules need."""

    id: UUID
    organization_id: UUID | None
    scope: ModelScope
    status: ModelStatus
    feature_schema_version: str
    requested_by_actor_id: UUID | None
    safety_constraints_preserved: bool


def ensure_transition(current: ModelStatus, target: ModelStatus) -> None:
    if not transition_allowed(current, target):
        raise VersionTransitionError(
            f"transition {current.value} -> {target.value} is not permitted"
        )


def ensure_same_organization(version: VersionView, organization_id: UUID) -> None:
    """A tenant may only act on its own versions; global versions are operations-plane only."""
    if version.scope is ModelScope.GLOBAL:
        raise VersionTransitionError("global versions require platform administration")
    if version.organization_id != organization_id:
        raise VersionTransitionError("model version belongs to a different organization")


def ensure_approver_distinct(version: VersionView, approver_actor_id: UUID | None) -> None:
    """Separation of duties: whoever requested a candidate may not approve it."""
    if (
        version.requested_by_actor_id is not None
        and approver_actor_id is not None
        and version.requested_by_actor_id == approver_actor_id
    ):
        raise VersionTransitionError(
            "separation of duties: the requesting actor cannot approve their own candidate"
        )


def ensure_schema_compatible(
    version: VersionView, current_schema: str = FEATURE_SCHEMA_VERSION
) -> None:
    if version.feature_schema_version != current_schema:
        raise VersionTransitionError(
            f"feature schema mismatch: version targets {version.feature_schema_version}, "
            f"runtime uses {current_schema}"
        )


def approve(
    version: VersionView, *, organization_id: UUID, approver_actor_id: UUID | None
) -> ModelStatus:
    ensure_same_organization(version, organization_id)
    ensure_transition(version.status, ModelStatus.APPROVED)
    ensure_approver_distinct(version, approver_actor_id)
    return ModelStatus.APPROVED


def activate(
    version: VersionView, *, organization_id: UUID, require_approval: bool = True
) -> ModelStatus:
    """Activation is reachable only from APPROVED (or a ROLLED_BACK version being restored)."""
    ensure_same_organization(version, organization_id)
    if require_approval and version.status not in (ModelStatus.APPROVED, ModelStatus.ROLLED_BACK):
        raise VersionTransitionError(
            f"activation requires an approved version; status is {version.status.value}"
        )
    ensure_transition(version.status, ModelStatus.ACTIVE)
    ensure_schema_compatible(version)
    if not version.safety_constraints_preserved:
        raise VersionTransitionError(
            "activation blocked: candidate did not preserve deterministic safety constraints"
        )
    return ModelStatus.ACTIVE


def rollback(version: VersionView, *, organization_id: UUID, reason: str) -> ModelStatus:
    ensure_same_organization(version, organization_id)
    ensure_transition(version.status, ModelStatus.ROLLED_BACK)
    if not reason.strip():
        raise VersionTransitionError("rollback requires a reason")
    return ModelStatus.ROLLED_BACK
