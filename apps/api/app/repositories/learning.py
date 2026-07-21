# Purpose: organization-scoped persistence for the controlled learning engine.
# Responsibilities: append immutable snapshots/events, record idempotent outcomes and revisioned
#   analyst feedback, load bounded per-organization observation batches for offline calibration, and
#   manage the reviewed model-version lifecycle. EVERY query filters by organization_id — there is
#   no cross-tenant read path. Dependencies: records, learning domain, learning services.
from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain.learning import (
    FEATURE_SCHEMA_VERSION,
    METHODOLOGY_VERSION,
    CalibrationReport,
    FeedbackType,
    LearningEventType,
    ModelScope,
    ModelStatus,
    NormalizedFeatures,
    OutcomeType,
)
from app.models.records import (
    AnalystFeedbackRecord,
    FeatureSnapshotRecord,
    LearningEventRecord,
    LearningModelVersionRecord,
    LearningRecommendationRecord,
    OperationalResultRecord,
    PlacementOutcomeRecord,
)
from app.services.learning.calibration import OutcomeObservation
from app.services.learning.events import learning_event_hash
from app.services.learning.features import assert_minimized, feature_hash


def _now() -> datetime:
    return datetime.now(UTC)


class LearningRepository:
    """All reads and writes are bound to one organization."""

    def __init__(self, session: Session, organization_id: UUID) -> None:
        self._session = session
        self._org = organization_id

    # -- feature snapshots --------------------------------------------------------------------

    def record_feature_snapshot(
        self,
        features: NormalizedFeatures,
        *,
        source_type: str,
        source_id_hash: str,
        expires_at: datetime | None = None,
    ) -> FeatureSnapshotRecord:
        """Deduplicated by (organization, feature_hash). Minimization is enforced before write."""
        assert_minimized(features)
        digest = feature_hash(features)
        existing = self._session.scalars(
            select(FeatureSnapshotRecord).where(
                FeatureSnapshotRecord.organization_id == self._org,
                FeatureSnapshotRecord.feature_hash == digest,
            )
        ).first()
        if existing is not None:
            return existing
        record = FeatureSnapshotRecord(
            organization_id=self._org,
            source_type=source_type,
            source_id_hash=source_id_hash,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            normalized_features=features.model_dump_json(),
            feature_hash=digest,
            expires_at=expires_at,
        )
        self._session.add(record)
        self._session.flush()
        self._append_event(
            LearningEventType.FEATURE_SNAPSHOT_CAPTURED, feature_snapshot_id=record.id
        )
        return record

    # -- recommendations + outcomes -----------------------------------------------------------

    def record_recommendation(
        self,
        *,
        snapshot_id: UUID | None,
        recommendation_type: str,
        target_zone: str,
        decoy_type: str,
        rank: int,
        confidence: float,
        reasoning_codes: tuple[str, ...],
        engine_version: str,
        model_version_id: UUID | None = None,
        target_category: str = "",
    ) -> LearningRecommendationRecord:
        record = LearningRecommendationRecord(
            organization_id=self._org,
            source_feature_snapshot_id=snapshot_id,
            recommendation_type=recommendation_type[:64],
            target_zone=target_zone[:64],
            target_category=target_category[:64],
            decoy_type=decoy_type[:64],
            rank=rank,
            confidence=confidence,
            reasoning_codes=json.dumps(list(reasoning_codes)[:20]),
            engine_version=engine_version[:32],
            model_version_id=model_version_id,
        )
        self._session.add(record)
        self._session.flush()
        self._append_event(LearningEventType.RECOMMENDATION_RECORDED, recommendation_id=record.id)
        return record

    def record_outcome(
        self,
        recommendation_id: UUID,
        outcome_type: OutcomeType,
        *,
        reason_code: str | None = None,
        observed_at: datetime | None = None,
        safe_metadata: dict[str, object] | None = None,
    ) -> PlacementOutcomeRecord:
        """Idempotent per (recommendation, outcome_type): a replayed outcome creates nothing."""
        recommendation = self._session.get(LearningRecommendationRecord, recommendation_id)
        if recommendation is None or recommendation.organization_id != self._org:
            raise PermissionError("recommendation does not belong to this organization")
        existing = self._session.scalars(
            select(PlacementOutcomeRecord).where(
                PlacementOutcomeRecord.recommendation_id == recommendation_id,
                PlacementOutcomeRecord.outcome_type == outcome_type.value,
            )
        ).first()
        if existing is not None:
            return existing
        record = PlacementOutcomeRecord(
            organization_id=self._org,
            recommendation_id=recommendation_id,
            outcome_type=outcome_type.value,
            outcome_reason_code=(reason_code or None),
            observed_at=observed_at or _now(),
            safe_metadata=json.dumps(safe_metadata or {})[:4000],
        )
        self._session.add(record)
        self._session.flush()
        self._append_event(
            LearningEventType.OUTCOME_RECORDED,
            recommendation_id=recommendation_id,
            placement_outcome_id=record.id,
        )
        return record

    # -- analyst feedback ---------------------------------------------------------------------

    def record_feedback(
        self,
        *,
        actor_id: UUID | None,
        target_kind: str,
        target_id: UUID,
        feedback_type: FeedbackType,
        original_value: str | None = None,
        corrected_value: str | None = None,
        normalized_comment: str | None = None,
    ) -> AnalystFeedbackRecord:
        """One record per (actor, target, revision). A revision appends; it never overwrites."""
        prior = self._session.scalars(
            select(AnalystFeedbackRecord)
            .where(
                AnalystFeedbackRecord.organization_id == self._org,
                AnalystFeedbackRecord.actor_id == actor_id,
                AnalystFeedbackRecord.target_kind == target_kind,
                AnalystFeedbackRecord.target_id == target_id,
            )
            .order_by(AnalystFeedbackRecord.revision.desc())
        ).first()
        # Identical resubmission is a no-op so repeated clicks cannot inflate evidence.
        if prior is not None and prior.feedback_type == feedback_type.value:
            return prior
        record = AnalystFeedbackRecord(
            organization_id=self._org,
            actor_id=actor_id,
            target_kind=target_kind[:24],
            target_id=target_id,
            revision=(prior.revision + 1) if prior is not None else 1,
            feedback_type=feedback_type.value,
            original_value=(original_value or None),
            corrected_value=(corrected_value or None),
            normalized_comment=normalized_comment,
        )
        self._session.add(record)
        self._session.flush()
        self._append_event(
            LearningEventType.ANALYST_FEEDBACK_SUBMITTED,
            analyst_feedback_id=record.id,
            actor_id=actor_id,
        )
        return record

    def feedback_for_target(
        self, target_kind: str, target_id: UUID
    ) -> tuple[AnalystFeedbackRecord, ...]:
        return tuple(
            self._session.scalars(
                select(AnalystFeedbackRecord).where(
                    AnalystFeedbackRecord.organization_id == self._org,
                    AnalystFeedbackRecord.target_kind == target_kind,
                    AnalystFeedbackRecord.target_id == target_id,
                )
            ).all()
        )

    # -- operational results ------------------------------------------------------------------

    def record_operational_result(
        self,
        *,
        operation_type: str,
        status: str,
        source_id: UUID | None = None,
        latency_ms: float | None = None,
        retry_count: int = 0,
        failure_category: str | None = None,
        sensor_health: float | None = None,
    ) -> OperationalResultRecord:
        record = OperationalResultRecord(
            organization_id=self._org,
            operation_type=operation_type[:48],
            status=status[:24],
            source_id=source_id,
            latency_ms=latency_ms,
            retry_count=retry_count,
            failure_category=failure_category,
            sensor_health=sensor_health,
        )
        self._session.add(record)
        self._session.flush()
        self._append_event(
            LearningEventType.OPERATIONAL_RESULT_RECORDED, operational_result_id=record.id
        )
        return record

    # -- immutable events ---------------------------------------------------------------------

    def _append_event(
        self,
        event_type: LearningEventType,
        *,
        feature_snapshot_id: UUID | None = None,
        recommendation_id: UUID | None = None,
        placement_outcome_id: UUID | None = None,
        analyst_feedback_id: UUID | None = None,
        operational_result_id: UUID | None = None,
        actor_id: UUID | None = None,
    ) -> LearningEventRecord | None:
        occurred_at = _now()
        digest = learning_event_hash(
            organization_id=self._org,
            event_type=event_type.value,
            occurred_at=occurred_at,
            feature_snapshot_id=feature_snapshot_id,
            recommendation_id=recommendation_id,
            placement_outcome_id=placement_outcome_id,
            analyst_feedback_id=analyst_feedback_id,
            operational_result_id=operational_result_id,
        )
        duplicate = self._session.scalars(
            select(LearningEventRecord).where(
                LearningEventRecord.organization_id == self._org,
                LearningEventRecord.event_hash == digest,
            )
        ).first()
        if duplicate is not None:
            return duplicate
        record = LearningEventRecord(
            organization_id=self._org,
            event_type=event_type.value,
            feature_snapshot_id=feature_snapshot_id,
            recommendation_id=recommendation_id,
            placement_outcome_id=placement_outcome_id,
            analyst_feedback_id=analyst_feedback_id,
            operational_result_id=operational_result_id,
            actor_id=actor_id,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            event_hash=digest,
            occurred_at=occurred_at,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def event_count(self) -> int:
        return len(
            self._session.scalars(
                select(LearningEventRecord.id).where(
                    LearningEventRecord.organization_id == self._org
                )
            ).all()
        )

    # -- calibration input --------------------------------------------------------------------

    def observations(
        self, *, window_start: datetime, window_end: datetime, limit: int = 5000
    ) -> list[OutcomeObservation]:
        """Bounded, organization-scoped observation batch. No cross-tenant join is possible here."""
        rows = self._session.execute(
            select(PlacementOutcomeRecord, LearningRecommendationRecord)
            .join(
                LearningRecommendationRecord,
                PlacementOutcomeRecord.recommendation_id == LearningRecommendationRecord.id,
            )
            .where(
                PlacementOutcomeRecord.organization_id == self._org,
                LearningRecommendationRecord.organization_id == self._org,
                PlacementOutcomeRecord.observed_at >= window_start,
                PlacementOutcomeRecord.observed_at <= window_end,
            )
            .order_by(PlacementOutcomeRecord.observed_at, PlacementOutcomeRecord.id)
            .limit(limit)
        ).all()

        observations: list[OutcomeObservation] = []
        for outcome, recommendation in rows:
            metadata = json.loads(outcome.safe_metadata or "{}")
            observations.append(
                OutcomeObservation(
                    cohort=recommendation.target_zone,
                    outcome_type=OutcomeType(outcome.outcome_type),
                    actor_id=str(metadata.get("actor_id")) if metadata.get("actor_id") else None,
                    observation_hours=float(metadata.get("observation_hours", 0.0)),
                    healthy_monitoring_ratio=float(metadata.get("healthy_monitoring_ratio", 1.0)),
                    predicted_confidence=recommendation.confidence,
                )
            )
        return observations

    # -- model versions -----------------------------------------------------------------------

    def create_candidate(
        self,
        report: CalibrationReport,
        *,
        algorithm_name: str,
        algorithm_version: str,
        requested_by_actor_id: UUID | None,
    ) -> LearningModelVersionRecord:
        record = LearningModelVersionRecord(
            organization_id=self._org,
            scope=ModelScope.ORGANIZATION.value,
            algorithm_name=algorithm_name[:64],
            algorithm_version=algorithm_version[:32],
            feature_schema_version=report.feature_schema_version,
            methodology_version=METHODOLOGY_VERSION,
            training_window_start=report.training_window_start,
            training_window_end=report.training_window_end,
            training_event_count=report.included_event_count,
            weights=report.candidate_weights.model_dump_json(),
            metrics=report.metrics.model_dump_json(),
            report=report.model_dump_json(),
            status=ModelStatus.CANDIDATE.value,
            requested_by_actor_id=requested_by_actor_id,
            safety_constraints_preserved=report.safety_constraints_preserved,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def get_version(self, version_id: UUID) -> LearningModelVersionRecord | None:
        record = self._session.get(LearningModelVersionRecord, version_id)
        if record is None or record.organization_id != self._org:
            return None
        return record

    def list_versions(self, *, limit: int = 50) -> tuple[LearningModelVersionRecord, ...]:
        return tuple(
            self._session.scalars(
                select(LearningModelVersionRecord)
                .where(LearningModelVersionRecord.organization_id == self._org)
                .order_by(LearningModelVersionRecord.created_at.desc())
                .limit(limit)
            ).all()
        )

    def active_version(self) -> LearningModelVersionRecord | None:
        return self._session.scalars(
            select(LearningModelVersionRecord).where(
                LearningModelVersionRecord.organization_id == self._org,
                LearningModelVersionRecord.status == ModelStatus.ACTIVE.value,
            )
        ).first()

    def set_status(
        self,
        record: LearningModelVersionRecord,
        status: ModelStatus,
        *,
        approver_actor_id: UUID | None = None,
        rollback_reason: str | None = None,
    ) -> LearningModelVersionRecord:
        """Applies a validated transition. Activation demotes the previous active version."""
        if status is ModelStatus.ACTIVE:
            previous = self.active_version()
            if previous is not None and previous.id != record.id:
                # The prior version is archived, never deleted, so rollback stays possible.
                previous.status = ModelStatus.ARCHIVED.value
            record.activated_at = _now()
        if status is ModelStatus.APPROVED:
            record.approved_by_actor_id = approver_actor_id
            record.approved_at = _now()
        if status is ModelStatus.ROLLED_BACK:
            record.rollback_reason = (rollback_reason or "")[:256]
        record.status = status.value
        self._session.flush()
        return record
