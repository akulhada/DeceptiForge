# Purpose: the controlled failover control plane.
# Responsibilities: drive the failover state machine with separation of duties (request vs approve
#   by different actors), fencing preconditions (a secondary is never promoted before the primary is
#   fenced), and an audited transition per step. Failback cannot begin before recovery validation.
#   No infrastructure calls — this records intent + state; scripts/operators perform the physical
#   promotion. Dependencies: repository, reliability domain, settings.
from __future__ import annotations

from uuid import UUID

from app.config.settings import Settings
from app.models.domain.reliability import (
    FailoverState,
    InvalidFailoverTransitionError,
    assert_transition,
)
from app.repositories.reliability import ReliabilityRepository


class FailoverError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class FailoverService:
    def __init__(self, repo: ReliabilityRepository, settings: Settings) -> None:
        self._repo = repo
        self._settings = settings

    def _transition(
        self, target: FailoverState, *, requested_by: UUID | None, approved_by: UUID | None,
        reason: str,
    ) -> FailoverState:
        current = self._repo.current_state()
        try:
            assert_transition(current, target)
        except InvalidFailoverTransitionError as error:
            raise FailoverError(409, str(error)) from None
        self._repo.record_transition(
            from_state=current, to_state=target,
            deployment_region=self._settings.deployment_region,
            cluster_id=self._settings.cluster_id, epoch=self._settings.active_region_epoch,
            requested_by=requested_by, approved_by=approved_by, reason=reason,
        )
        return target

    def request_failover(self, *, actor_id: UUID | None, reason: str) -> FailoverState:
        return self._transition(
            FailoverState.FAILOVER_REQUESTED, requested_by=actor_id, approved_by=None,
            reason=reason,
        )

    def approve_failover(self, *, actor_id: UUID | None, reason: str) -> FailoverState:
        """Approve a pending failover and fence the primary. Separation of duties: the approver must
        differ from the requester when approval is required."""
        request = self._repo.latest_request()
        if request is None or self._repo.current_state() != FailoverState.FAILOVER_REQUESTED:
            raise FailoverError(409, "no pending failover request")
        if (
            self._settings.regional_failover_requires_approval
            and actor_id is not None
            and request.requested_by_actor_id is not None
            and actor_id == request.requested_by_actor_id
        ):
            raise FailoverError(403, "a separate operator must approve the failover")
        # Approval advances to PRIMARY_FENCED — the secondary is only promotable after this.
        return self._transition(
            FailoverState.PRIMARY_FENCED, requested_by=request.requested_by_actor_id,
            approved_by=actor_id, reason=reason,
        )

    def advance(
        self, target: FailoverState, *, actor_id: UUID | None, reason: str
    ) -> FailoverState:
        """Advance an operational step (promote/validate/failback/restore). The state machine
        enforces ordering — e.g. FAILBACK_PENDING is only reachable from RECOVERY_VALIDATION, so
        failback cannot start before resynchronization is validated."""
        return self._transition(target, requested_by=None, approved_by=actor_id, reason=reason)
