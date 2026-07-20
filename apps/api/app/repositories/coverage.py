# Purpose: organization-scoped persistence for coverage snapshots, surfaces, gaps, recommendations,
#   policy, and audit.
# Responsibilities: persist an immutable snapshot (idempotent by source_state_hash + methodology
#   version so concurrent/scheduled runs never duplicate), upsert the pre-aggregated surface state
#   for fast reads, store per-snapshot gaps + ranked recommendations, read history without
#   recomputing, and manage the versioned policy. Never stores raw evidence or secrets.
# Dependencies: records, coverage domain.
from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain.coverage import CoveragePolicyDoc, CoverageResult
from app.models.records import (
    CoverageAuditRecord,
    CoverageGapRecord,
    CoveragePolicyRecord,
    CoverageSnapshotRecord,
    CoverageSurfaceRecord,
    PlacementRecommendationRecord,
)


def _now() -> datetime:
    return datetime.now(UTC)


class CoverageRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # -- snapshots (immutable) ----------------------------------------------------------------

    def latest_snapshot(self, org: UUID) -> CoverageSnapshotRecord | None:
        return self._session.scalars(
            select(CoverageSnapshotRecord)
            .where(CoverageSnapshotRecord.organization_id == org)
            .order_by(CoverageSnapshotRecord.calculated_at.desc())
            .limit(1)
        ).first()

    def persist_snapshot(
        self, org: UUID, result: CoverageResult, *, now: datetime | None = None
    ) -> tuple[CoverageSnapshotRecord, bool]:
        """Persist an immutable snapshot. Idempotent: if the most recent snapshot already reflects
        the same source state under the same methodology, return it and create nothing new."""
        now = now or _now()
        latest = self.latest_snapshot(org)
        if (
            latest is not None
            and latest.source_state_hash == result.source_state_hash
            and latest.methodology_version == result.methodology_version
        ):
            return latest, False
        surfaces_blob = json.dumps([s.model_dump(mode="json") for s in result.surfaces])
        snapshot = CoverageSnapshotRecord(
            organization_id=org, calculated_at=now, overall_score=result.overall_score,
            confidence=result.confidence, covered_weight=result.covered_weight,
            total_weight=result.total_weight, unknown_weight=result.unknown_weight,
            active_decoys=result.active_decoys, active_sensors=result.active_sensors,
            unhealthy_sensors=result.unhealthy_sensors, expired_decoys=result.expired_decoys,
            blind_spot_count=result.blind_spot_count,
            methodology_version=result.methodology_version,
            source_state_hash=result.source_state_hash, surfaces_data=surfaces_blob,
        )
        self._session.add(snapshot)
        self._session.flush()
        for gap in result.gaps:
            self._session.add(CoverageGapRecord(
                organization_id=org, snapshot_id=snapshot.id,
                surface_type=gap.surface_type.value,
                external_or_resource_id=gap.external_or_resource_id[:512],
                gap_type=gap.gap_type.value, severity=gap.severity.value, reason=gap.reason[:512],
                missing_controls=",".join(gap.missing_controls)[:512],
                recommended_decoy_type=gap.recommended_decoy_type,
                recommended_sensor_type=gap.recommended_sensor_type,
                expected_coverage_gain=gap.expected_coverage_gain,
            ))
        for rec in result.recommendations:
            self._session.add(PlacementRecommendationRecord(
                organization_id=org, snapshot_id=snapshot.id,
                surface_type=rec.surface_type.value,
                external_or_resource_id=rec.external_or_resource_id[:512],
                recommended_action=rec.recommended_action.value,
                recommended_decoy_type=rec.recommended_decoy_type,
                target_location=rec.target_location[:512],
                expected_coverage_gain=rec.expected_coverage_gain,
                expected_detection_gain=rec.expected_detection_gain,
                deployment_risk=rec.deployment_risk, false_positive_risk=rec.false_positive_risk,
                implementation_effort=rec.implementation_effort, priority_score=rec.priority_score,
                confidence=rec.confidence, explanation=rec.explanation[:512],
            ))
        self._upsert_surfaces(org, result, now)
        self._session.flush()
        return snapshot, True

    def _upsert_surfaces(self, org: UUID, result: CoverageResult, now: datetime) -> None:
        existing = {
            (r.surface_type, r.external_or_resource_id): r
            for r in self._session.scalars(
                select(CoverageSurfaceRecord).where(CoverageSurfaceRecord.organization_id == org)
            ).all()
        }
        for cov in result.surfaces:
            s = cov.surface
            key = (s.surface_type.value, s.external_or_resource_id)
            record = existing.get(key)
            if record is None:
                record = CoverageSurfaceRecord(
                    organization_id=org, surface_type=s.surface_type.value,
                    external_or_resource_id=s.external_or_resource_id[:512],
                    display_name=s.display_name[:256], criticality=s.criticality,
                    exposure_score=s.exposure_score, sensitivity_score=s.sensitivity_score,
                    attack_likelihood=s.attack_likelihood, business_impact=s.business_impact,
                    coverage_requirement=s.coverage_requirement, risk_weight=s.risk_weight,
                    surface_coverage=cov.surface_coverage, confidence=cov.confidence,
                    status="unknown" if cov.is_unknown else "known",
                )
                self._session.add(record)
            else:
                record.criticality = s.criticality
                record.risk_weight = s.risk_weight
                record.surface_coverage = cov.surface_coverage
                record.confidence = cov.confidence
                record.status = "unknown" if cov.is_unknown else "known"
                record.updated_at = now

    def list_snapshots(self, org: UUID, *, limit: int = 50) -> tuple[CoverageSnapshotRecord, ...]:
        return tuple(
            self._session.scalars(
                select(CoverageSnapshotRecord)
                .where(CoverageSnapshotRecord.organization_id == org)
                .order_by(CoverageSnapshotRecord.calculated_at.desc())
                .limit(limit)
            ).all()
        )

    def get_snapshot(self, org: UUID, snapshot_id: UUID) -> CoverageSnapshotRecord | None:
        record = self._session.get(CoverageSnapshotRecord, snapshot_id)
        if record is None or record.organization_id != org:
            return None
        return record

    def surfaces(self, org: UUID) -> tuple[CoverageSurfaceRecord, ...]:
        return tuple(
            self._session.scalars(
                select(CoverageSurfaceRecord)
                .where(CoverageSurfaceRecord.organization_id == org)
                .order_by(CoverageSurfaceRecord.risk_weight.desc())
            ).all()
        )

    def gaps(self, org: UUID, snapshot_id: UUID) -> tuple[CoverageGapRecord, ...]:
        return tuple(
            self._session.scalars(
                select(CoverageGapRecord).where(
                    CoverageGapRecord.organization_id == org,
                    CoverageGapRecord.snapshot_id == snapshot_id,
                ).order_by(CoverageGapRecord.severity)
            ).all()
        )

    def recommendations(
        self, org: UUID, snapshot_id: UUID
    ) -> tuple[PlacementRecommendationRecord, ...]:
        return tuple(
            self._session.scalars(
                select(PlacementRecommendationRecord).where(
                    PlacementRecommendationRecord.organization_id == org,
                    PlacementRecommendationRecord.snapshot_id == snapshot_id,
                ).order_by(PlacementRecommendationRecord.priority_score.desc())
            ).all()
        )

    def get_recommendation(
        self, org: UUID, recommendation_id: UUID
    ) -> PlacementRecommendationRecord | None:
        record = self._session.get(PlacementRecommendationRecord, recommendation_id)
        if record is None or record.organization_id != org:
            return None
        return record

    # -- policy -------------------------------------------------------------------------------

    def get_policy(self, org: UUID) -> CoveragePolicyRecord | None:
        return self._session.scalars(
            select(CoveragePolicyRecord).where(CoveragePolicyRecord.organization_id == org)
        ).first()

    def upsert_policy(self, org: UUID, doc: CoveragePolicyDoc) -> CoveragePolicyRecord:
        record = self.get_policy(org)
        data = json.dumps(doc.model_dump(mode="json", exclude={"organization_id"}))
        if record is None:
            record = CoveragePolicyRecord(organization_id=org, data=data, policy_version=1)
            self._session.add(record)
        else:
            record.data = data
            record.policy_version += 1
            record.updated_at = _now()
        self._session.flush()
        return record

    # -- audit --------------------------------------------------------------------------------

    def add_audit(
        self, *, organization_id: UUID, event_type: str, request_id: str,
        actor_id: UUID | None = None, snapshot_id: UUID | None = None, safe_metadata: str = "",
    ) -> None:
        self._session.add(CoverageAuditRecord(
            organization_id=organization_id, actor_id=actor_id, snapshot_id=snapshot_id,
            event_type=event_type, request_id=request_id, safe_metadata=safe_metadata[:1024],
        ))
        self._session.flush()
