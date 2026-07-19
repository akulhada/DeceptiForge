# Purpose: organization-scoped persistence for decoy deployments, items, approvals, audit, jobs, and
#   tripwire activations.
# Responsibilities: enforce organization scoping on every read/write, apply state-machine-checked
#   status transitions, dedup deployment jobs (no duplicate PR), claim jobs atomically, and activate
#   tripwires idempotently. Never stores tokens or raw repository content. Dependencies: records,
#   deployment domain state machine.
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.domain.deployment import (
    ChangeSetItem,
    DeploymentPreview,
    DeploymentStatus,
    assert_transition,
)
from app.models.records import (
    DecoyDeploymentItemRecord,
    DecoyDeploymentRecord,
    DeploymentApprovalRecord,
    DeploymentAuditRecord,
    DeploymentJobRecord,
    DeploymentTripwireRecord,
)


def _now() -> datetime:
    return datetime.now(UTC)


class DeploymentNotFoundError(Exception):
    """Raised when a deployment does not exist for the organization."""


class DeploymentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # -- deployments --------------------------------------------------------------------------

    def create(
        self,
        *,
        organization_id: UUID,
        repository_id: UUID,
        decoy_plan_id: UUID,
        validation_decision: str,
        requested_by_actor_id: UUID | None,
        target_branch: str,
        source_branch: str,
        base_commit_sha: str,
        expires_at: datetime | None,
    ) -> DecoyDeploymentRecord:
        record = DecoyDeploymentRecord(
            organization_id=organization_id,
            repository_id=repository_id,
            decoy_plan_id=decoy_plan_id,
            validation_report_decision=validation_decision,
            requested_by_actor_id=requested_by_actor_id,
            status=DeploymentStatus.DRAFT.value,
            target_branch=target_branch,
            source_branch=source_branch,
            base_commit_sha=base_commit_sha,
            expires_at=expires_at,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def get(self, organization_id: UUID, deployment_id: UUID) -> DecoyDeploymentRecord:
        record = self._session.get(DecoyDeploymentRecord, deployment_id)
        if record is None or record.organization_id != organization_id:
            raise DeploymentNotFoundError(str(deployment_id))
        return record

    def get_any(self, deployment_id: UUID) -> DecoyDeploymentRecord | None:
        return self._session.get(DecoyDeploymentRecord, deployment_id)

    def list(self, organization_id: UUID) -> tuple[DecoyDeploymentRecord, ...]:
        rows = self._session.scalars(
            select(DecoyDeploymentRecord)
            .where(DecoyDeploymentRecord.organization_id == organization_id)
            .order_by(DecoyDeploymentRecord.created_at.desc())
        ).all()
        return tuple(rows)

    def set_preview(
        self, record: DecoyDeploymentRecord, preview: DeploymentPreview, contents: dict[UUID, str]
    ) -> None:
        """Persist the preview and its change-set items (replacing any prior planned items)."""
        for existing in self.get_items(record.id):
            self._session.delete(existing)
        record.preview_hash = preview.preview_hash
        record.preview_data = preview.model_dump_json()
        record.target_branch = preview.target_branch
        record.base_commit_sha = preview.base_commit_sha
        record.expires_at = preview.expires_at
        record.updated_at = _now()
        for item in preview.items:
            self._session.add(
                DecoyDeploymentItemRecord(
                    deployment_id=record.id,
                    decoy_id=item.decoy_id,
                    target_path=item.target_path,
                    operation=item.operation.value,
                    trace_identifier=item.trace_identifier,
                    original_content_hash=item.original_content_hash,
                    proposed_content_hash=item.proposed_content_hash,
                    content_data=contents[item.decoy_id],
                    status="planned",
                )
            )
        self._session.flush()

    def load_preview(self, record: DecoyDeploymentRecord) -> DeploymentPreview | None:
        if record.preview_data is None:
            return None
        return DeploymentPreview.model_validate_json(record.preview_data)

    def get_items(self, deployment_id: UUID) -> tuple[DecoyDeploymentItemRecord, ...]:
        rows = self._session.scalars(
            select(DecoyDeploymentItemRecord)
            .where(DecoyDeploymentItemRecord.deployment_id == deployment_id)
            .order_by(DecoyDeploymentItemRecord.target_path)
        ).all()
        return tuple(rows)

    def transition(
        self, record: DecoyDeploymentRecord, target: DeploymentStatus, **fields: Any
    ) -> None:
        """Apply a state-machine-checked status transition and optional field updates."""
        assert_transition(DeploymentStatus(record.status), target)
        record.status = target.value
        for key, value in fields.items():
            setattr(record, key, value)
        record.updated_at = _now()
        self._session.flush()

    # -- approvals + audit --------------------------------------------------------------------

    def add_approval(
        self,
        *,
        organization_id: UUID,
        deployment_id: UUID,
        actor_id: UUID | None,
        decision: str,
        comment: str | None,
    ) -> None:
        self._session.add(
            DeploymentApprovalRecord(
                organization_id=organization_id,
                deployment_id=deployment_id,
                actor_id=actor_id,
                decision=decision,
                comment=comment,
            )
        )
        self._session.flush()

    def add_audit(
        self,
        *,
        organization_id: UUID,
        deployment_id: UUID,
        actor_id: UUID | None,
        event_type: str,
        request_id: str,
        safe_metadata: str = "",
    ) -> None:
        self._session.add(
            DeploymentAuditRecord(
                organization_id=organization_id,
                deployment_id=deployment_id,
                actor_id=actor_id,
                event_type=event_type,
                request_id=request_id,
                safe_metadata=safe_metadata[:1024],
            )
        )
        self._session.flush()

    def audit_events(self, deployment_id: UUID) -> tuple[DeploymentAuditRecord, ...]:
        rows = self._session.scalars(
            select(DeploymentAuditRecord)
            .where(DeploymentAuditRecord.deployment_id == deployment_id)
            .order_by(DeploymentAuditRecord.created_at)
        ).all()
        return tuple(rows)

    # -- job queue ----------------------------------------------------------------------------

    def enqueue_job(
        self, *, organization_id: UUID, deployment_id: UUID, job_type: str, correlation_id: str
    ) -> bool:
        """Enqueue a job; return False if one already exists (unique per deployment+type).

        The uniqueness prevents a duplicate deploy request from creating a second pull request.
        """
        try:
            with self._session.begin_nested():
                self._session.add(
                    DeploymentJobRecord(
                        organization_id=organization_id,
                        deployment_id=deployment_id,
                        job_type=job_type,
                        status="pending",
                        correlation_id=correlation_id,
                    )
                )
            return True
        except IntegrityError:
            return False

    def claim_jobs(self, limit: int) -> tuple[DeploymentJobRecord, ...]:
        candidate_ids = self._session.scalars(
            select(DeploymentJobRecord.id)
            .where(DeploymentJobRecord.status == "pending")
            .order_by(DeploymentJobRecord.created_at)
            .limit(limit)
        ).all()
        claimed: list[DeploymentJobRecord] = []
        for job_id in candidate_ids:
            result = self._session.execute(
                update(DeploymentJobRecord)
                .where(
                    DeploymentJobRecord.id == job_id,
                    DeploymentJobRecord.status == "pending",
                )
                .values(status="claimed", leased_until=_now())
            )
            if cast("CursorResult[Any]", result).rowcount == 1:
                record = self._session.get(DeploymentJobRecord, job_id)
                if record is not None:
                    record.attempts += 1
                    claimed.append(record)
        self._session.flush()
        return tuple(claimed)

    def complete_job(self, job_id: UUID, *, ok: bool) -> None:
        record = self._session.get(DeploymentJobRecord, job_id)
        if record is None:
            return
        record.status = "done" if ok else "failed"
        record.processed_at = _now()
        self._session.flush()

    def clear_job(self, deployment_id: UUID, job_type: str) -> None:
        """Remove a job row so a later lifecycle op (retire/rollback) can enqueue its own."""
        for record in self._session.scalars(
            select(DeploymentJobRecord).where(
                DeploymentJobRecord.deployment_id == deployment_id,
                DeploymentJobRecord.job_type == job_type,
            )
        ).all():
            self._session.delete(record)
        self._session.flush()

    # -- tripwire activation ------------------------------------------------------------------

    def activate_tripwires(
        self,
        *,
        organization_id: UUID,
        deployment_id: UUID,
        items: tuple[ChangeSetItem, ...],
        commit_sha: str,
    ) -> int:
        """Idempotently activate one tripwire per change-set item; return newly activated count."""
        activated = 0
        for item in items:
            try:
                with self._session.begin_nested():
                    self._session.add(
                        DeploymentTripwireRecord(
                            organization_id=organization_id,
                            deployment_id=deployment_id,
                            decoy_id=item.decoy_id,
                            trace_identifier=item.trace_identifier,
                            target_path=item.target_path,
                            commit_sha=commit_sha,
                            status="active",
                        )
                    )
                activated += 1
            except IntegrityError:
                continue  # already activated (idempotent)
        self._session.flush()
        return activated

    def set_tripwire_status(self, deployment_id: UUID, status: str) -> int:
        rows = self._session.scalars(
            select(DeploymentTripwireRecord).where(
                DeploymentTripwireRecord.deployment_id == deployment_id
            )
        ).all()
        for row in rows:
            row.status = status
        self._session.flush()
        return len(rows)

    def active_tripwires(self, deployment_id: UUID) -> tuple[DeploymentTripwireRecord, ...]:
        rows = self._session.scalars(
            select(DeploymentTripwireRecord).where(
                DeploymentTripwireRecord.deployment_id == deployment_id,
                DeploymentTripwireRecord.status == "active",
            )
        ).all()
        return tuple(rows)


def new_correlation_id() -> str:
    return uuid4().hex
