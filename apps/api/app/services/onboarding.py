"""State-derived, tenant-scoped guided activation; never bypasses existing safety controls."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.models.records import (
    ApiKeyRecord,
    CoverageSnapshotRecord,
    DecoyDeploymentRecord,
    DeploymentTripwireRecord,
    DetectionTestRunRecord,
    OnboardingRecommendationRecord,
    OnboardingStepRecord,
    OnboardingWorkspaceRecord,
    RepositoryRecord,
    SecurityIntegrationRecord,
)

_STEPS = (
    ("organization", "identity", "Configure a verified identity provider and administrator."),
    ("surfaces", "repository_inventory", "Connect and inventory at least one protected surface."),
    ("assessment", "repository_scan", "Complete a repository scan or inventory."),
    ("first_decoy", "verified_deployment", "Approve, deploy, verify, and activate monitoring."),
    ("detection_test", "detection_test", "Run a signed controlled detection test."),
    ("operations", "coverage", "Recalculate coverage after deployment."),
    ("operations", "integration", "Configure an operational integration."),
)


class OnboardingService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session, self._settings = session, settings

    def start(self, organization_id: UUID) -> OnboardingWorkspaceRecord:
        workspace = self._workspace(organization_id, create=True)
        if workspace.status in {"not_started", "paused"}:
            workspace.status, workspace.started_at = "in_progress", workspace.started_at or _now()
        self.reconcile(organization_id)
        return workspace

    def pause(self, organization_id: UUID) -> OnboardingWorkspaceRecord:
        workspace = self._workspace(organization_id, create=True)
        if workspace.status not in {"activated", "completed"}:
            workspace.status, workspace.updated_at = "paused", _now()
        return workspace

    def resume(self, organization_id: UUID) -> OnboardingWorkspaceRecord:
        workspace = self._workspace(organization_id, create=True)
        if workspace.status == "paused":
            workspace.status, workspace.updated_at = "in_progress", _now()
        self.reconcile(organization_id)
        return workspace

    def view(self, organization_id: UUID) -> dict[str, object]:
        workspace = self._workspace(organization_id, create=True)
        self.reconcile(organization_id)
        steps = tuple(
            self._session.scalars(
                select(OnboardingStepRecord)
                .where(OnboardingStepRecord.workspace_id == workspace.id)
                .order_by(OnboardingStepRecord.id)
            ).all()
        )
        return {
            "workspace": workspace,
            "steps": steps,
            "activated": workspace.activated_at is not None,
        }

    def recommendations(self, organization_id: UUID) -> tuple[OnboardingRecommendationRecord, ...]:
        workspace = self._workspace(organization_id, create=True)
        existing = tuple(
            self._session.scalars(
                select(OnboardingRecommendationRecord)
                .where(
                    OnboardingRecommendationRecord.workspace_id == workspace.id,
                    OnboardingRecommendationRecord.status == "active",
                )
                .order_by(OnboardingRecommendationRecord.priority.desc())
                .limit(10)
            ).all()
        )
        if existing:
            return existing
        # The only default first-decoy recommendation is a low-risk documentation/config asset.
        if (
            self._count(RepositoryRecord, organization_id)
            and self._count(DecoyDeploymentRecord, organization_id) == 0
        ):
            record = OnboardingRecommendationRecord(
                organization_id=organization_id,
                workspace_id=workspace.id,
                recommendation_type="safe_first_decoy",
                target_surface_type="repository",
                target_resource_id=None,
                priority=100,
                expected_activation_gain=0.2,
                expected_coverage_gain=0.1,
                implementation_effort="low",
                risk="low",
                explanation=(
                    "Create an inert documentation or configuration decoy through the normal "
                    "review and approval workflow."
                ),
            )
            self._session.add(record)
            self._session.flush()
            return (record,)
        return ()

    def decide_recommendation(
        self, organization_id: UUID, recommendation_id: UUID, status: str
    ) -> OnboardingRecommendationRecord | None:
        record = self._session.get(OnboardingRecommendationRecord, recommendation_id)
        if record is None or record.organization_id != organization_id or record.status != "active":
            return None
        record.status, record.updated_at = status, _now()
        return record

    def create_detection_test(
        self, organization_id: UUID, actor_id: UUID | None, deployment_id: UUID
    ) -> DetectionTestRunRecord:
        deployment = self._session.get(DecoyDeploymentRecord, deployment_id)
        if (
            deployment is None
            or deployment.organization_id != organization_id
            or deployment.status != "deployed"
            or deployment.monitoring_activated_at is None
        ):
            raise ValueError("deployment must be verified and monitoring active")
        tripwire = self._session.scalar(
            select(DeploymentTripwireRecord)
            .where(
                DeploymentTripwireRecord.organization_id == organization_id,
                DeploymentTripwireRecord.deployment_id == deployment_id,
                DeploymentTripwireRecord.status == "active",
            )
            .order_by(DeploymentTripwireRecord.activated_at)
            .limit(1)
        )
        if tripwire is None:
            raise ValueError("deployment has no active tripwire")
        record = DetectionTestRunRecord(
            organization_id=organization_id,
            requested_by_actor_id=actor_id,
            deployment_id=deployment_id,
            trace_identifier=tripwire.trace_identifier,
            status="running",
        )
        self._session.add(record)
        self._session.flush()
        return record

    def record_detection(
        self, organization_id: UUID, trace_identifier: str, event_id: UUID, alert_id: UUID | None
    ) -> None:
        """Called only after the signed ingestion pipeline persisted its normal event/alert."""
        run = self._session.scalar(
            select(DetectionTestRunRecord)
            .where(
                DetectionTestRunRecord.organization_id == organization_id,
                DetectionTestRunRecord.trace_identifier == trace_identifier,
                DetectionTestRunRecord.status == "running",
            )
            .order_by(DetectionTestRunRecord.started_at.desc())
            .limit(1)
        )
        if run is None:
            return
        run.observed_event_id, run.alert_id, run.status, run.completed_at = (
            event_id,
            alert_id,
            "detected",
            _now(),
        )

    def reconcile(self, organization_id: UUID) -> None:
        workspace = self._workspace(organization_id, create=True)
        if workspace.status == "paused":
            return
        facts = {
            "identity": self._identity_ready(organization_id),
            "repository_inventory": self._count(RepositoryRecord, organization_id) > 0,
            "repository_scan": self._count(RepositoryRecord, organization_id) > 0,
            "verified_deployment": self._verified_deployment(organization_id),
            "detection_test": self._count(
                DetectionTestRunRecord, organization_id, status="detected"
            )
            > 0,
            "coverage": self._coverage_ready(organization_id),
            "integration": self._count(SecurityIntegrationRecord, organization_id, status="active")
            > 0,
        }
        now = _now()
        for phase, key, message in _STEPS:
            step = self._session.scalar(
                select(OnboardingStepRecord).where(
                    OnboardingStepRecord.workspace_id == workspace.id,
                    OnboardingStepRecord.step_key == key,
                )
            )
            if step is None:
                step = OnboardingStepRecord(
                    organization_id=organization_id,
                    workspace_id=workspace.id,
                    phase=phase,
                    step_key=key,
                )
                self._session.add(step)
            complete = facts[key]
            step.status = (
                "completed"
                if complete
                else ("requires_attention" if step.completed_at else "blocked")
            )
            step.completed_at = now if complete else None
            step.blocked_reason_code = None if complete else f"{key}_required"
            step.safe_blocked_message = None if complete else message
            step.evidence, step.updated_at = (
                json.dumps(
                    {"methodology": self._settings.onboarding_version, "state_derived": True}
                ),
                now,
            )
        if all(facts.values()):
            workspace.status, workspace.current_phase = "activated", "operations"
            workspace.activated_at = workspace.activated_at or now
        else:
            workspace.status = "in_progress" if workspace.started_at else "not_started"
            workspace.current_phase = next(phase for phase, key, _ in _STEPS if not facts[key])
        workspace.updated_at = now
        self._session.flush()

    def _workspace(self, organization_id: UUID, *, create: bool) -> OnboardingWorkspaceRecord:
        row = self._session.scalar(
            select(OnboardingWorkspaceRecord).where(
                OnboardingWorkspaceRecord.organization_id == organization_id
            )
        )
        if row is None and create:
            row = OnboardingWorkspaceRecord(
                organization_id=organization_id,
                onboarding_version=self._settings.onboarding_version,
            )
            self._session.add(row)
            self._session.flush()
        assert row is not None
        return row

    def _identity_ready(self, organization_id: UUID) -> bool:
        if bool(self._settings.model_dump().get("onboarding_require_sso", True)):
            return False  # SSO provider state has no authoritative persistence yet; never infer it.
        return self._count(ApiKeyRecord, organization_id, role="owner", status="active") > 0

    def _verified_deployment(self, organization_id: UUID) -> bool:
        return (
            int(
                self._session.scalar(
                    select(func.count())
                    .select_from(DecoyDeploymentRecord)
                    .where(
                        DecoyDeploymentRecord.organization_id == organization_id,
                        DecoyDeploymentRecord.status == "deployed",
                        DecoyDeploymentRecord.monitoring_activated_at.is_not(None),
                    )
                )
                or 0
            )
            > 0
        )

    def _coverage_ready(self, organization_id: UUID) -> bool:
        latest = self._session.scalar(
            select(CoverageSnapshotRecord)
            .where(CoverageSnapshotRecord.organization_id == organization_id)
            .order_by(CoverageSnapshotRecord.calculated_at.desc())
            .limit(1)
        )
        return (
            latest is not None
            and latest.overall_score >= self._settings.onboarding_min_coverage_score
        )

    def _count(self, model: type[Any], organization_id: UUID, **filters: str) -> int:
        organization_column = model.organization_id
        query = (
            select(func.count()).select_from(model).where(organization_column == organization_id)
        )
        for field, value in filters.items():
            query = query.where(getattr(model, field) == value)
        return int(self._session.scalar(query) or 0)


def _now() -> datetime:
    return datetime.now(UTC)
