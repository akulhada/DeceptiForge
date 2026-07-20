# Purpose: persistence for reliability operational records — failover events, restore drills, audit.
# Responsibilities: append audited failover transitions (region/epoch/operator, SoD), record restore
#   drills with the signed report, read the current failover state + latest backup/drill, and append
#   reliability audit. Never stores secrets or provider responses. Dependencies: records, domain.
from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain.reliability import FailoverState, RestoreReport
from app.models.records import (
    FailoverEventRecord,
    ReliabilityAuditRecord,
    RestoreDrillRecord,
)


def _now() -> datetime:
    return datetime.now(UTC)


class ReliabilityRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # -- failover events ----------------------------------------------------------------------

    def current_state(self) -> FailoverState:
        latest = self._session.scalars(
            select(FailoverEventRecord).order_by(FailoverEventRecord.created_at.desc()).limit(1)
        ).first()
        return FailoverState(latest.to_state) if latest else FailoverState.NORMAL

    def record_transition(
        self, *, from_state: FailoverState, to_state: FailoverState, deployment_region: str,
        cluster_id: str, epoch: int, requested_by: UUID | None, approved_by: UUID | None,
        reason: str, safe_metadata: str = "",
    ) -> FailoverEventRecord:
        record = FailoverEventRecord(
            from_state=from_state.value, to_state=to_state.value,
            deployment_region=deployment_region[:64], cluster_id=cluster_id[:64],
            active_region_epoch=epoch, requested_by_actor_id=requested_by,
            approved_by_actor_id=approved_by, reason=reason[:512],
            safe_metadata=safe_metadata[:1024],
        )
        self._session.add(record)
        self._session.flush()
        return record

    def failover_events(self, *, limit: int = 50) -> tuple[FailoverEventRecord, ...]:
        return tuple(
            self._session.scalars(
                select(FailoverEventRecord)
                .order_by(FailoverEventRecord.created_at.desc())
                .limit(limit)
            ).all()
        )

    def latest_request(self) -> FailoverEventRecord | None:
        return self._session.scalars(
            select(FailoverEventRecord)
            .where(FailoverEventRecord.to_state == FailoverState.FAILOVER_REQUESTED.value)
            .order_by(FailoverEventRecord.created_at.desc())
            .limit(1)
        ).first()

    # -- restore drills -----------------------------------------------------------------------

    def record_drill(
        self, report: RestoreReport, *, deployment_region: str, requested_by: UUID | None
    ) -> RestoreDrillRecord:
        record = RestoreDrillRecord(
            backup_identifier=report.backup_identifier[:128], recovery_point=report.recovery_point,
            started_at=report.started_at, finished_at=report.finished_at,
            achieved_rpo_minutes=report.achieved_rpo_minutes,
            achieved_rto_minutes=report.achieved_rto_minutes,
            migration_revision=report.migration_revision[:64], passed=report.passed,
            checksum=report.checksum, report_data=report.model_dump_json(),
            deployment_region=deployment_region[:64], requested_by_actor_id=requested_by,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def latest_drill(self) -> RestoreDrillRecord | None:
        return self._session.scalars(
            select(RestoreDrillRecord).order_by(RestoreDrillRecord.created_at.desc()).limit(1)
        ).first()

    def drills(self, *, limit: int = 50) -> tuple[RestoreDrillRecord, ...]:
        return tuple(
            self._session.scalars(
                select(RestoreDrillRecord)
                .order_by(RestoreDrillRecord.created_at.desc())
                .limit(limit)
            ).all()
        )

    # -- audit --------------------------------------------------------------------------------

    def add_audit(
        self, *, event_type: str, request_id: str, deployment_region: str,
        actor_id: UUID | None = None, safe_metadata: str = "",
    ) -> None:
        self._session.add(ReliabilityAuditRecord(
            actor_id=actor_id, event_type=event_type, request_id=request_id,
            deployment_region=deployment_region[:64], safe_metadata=safe_metadata[:1024],
        ))
        self._session.flush()


def current_migration_head() -> str:
    """The migration revision this build expects (the alembic head)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config()
    config.set_main_option("script_location", "migrations")
    return ScriptDirectory.from_config(config).get_current_head() or ""


def _serialize_report(report: RestoreReport) -> str:
    return json.dumps(report.model_dump(mode="json"))
