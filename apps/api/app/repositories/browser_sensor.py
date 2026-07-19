# Purpose: organization-scoped persistence for browser AI policy, minimized paste events, and audit.
# Responsibilities: read/update the versioned policy (monotonic policy_version), store only
#   minimized events (never pasted text or conversation), and append audit rows. Never returns or
#   logs secrets, signatures, or raw content. Dependencies: records, browser domain, minimize.
from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain.browser_sensor import DomainRule, MinimizedBrowserEvent
from app.models.records import (
    BrowserAiPolicyRecord,
    BrowserEventRecord,
    BrowserSensorAuditRecord,
)
from app.services.browser_sensor.minimize import serialize_metadata


def _now() -> datetime:
    return datetime.now(UTC)


class BrowserSensorRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # -- policy -------------------------------------------------------------------------------

    def get_policy(self, organization_id: UUID) -> BrowserAiPolicyRecord | None:
        return self._session.scalars(
            select(BrowserAiPolicyRecord).where(
                BrowserAiPolicyRecord.organization_id == organization_id
            )
        ).first()

    def upsert_policy(
        self,
        organization_id: UUID,
        *,
        enabled: bool,
        trace_match_mode: str,
        local_only_mode: bool,
        event_reporting_enabled: bool,
        show_user_notification: bool,
        allow_pause: bool,
        min_extension_version: str,
        rules: tuple[DomainRule, ...],
    ) -> BrowserAiPolicyRecord:
        record = self.get_policy(organization_id)
        rules_data = json.dumps(
            [{"domain": r.domain, "classification": r.classification.value} for r in rules]
        )
        if record is None:
            record = BrowserAiPolicyRecord(
                organization_id=organization_id, enabled=enabled,
                trace_match_mode=trace_match_mode, local_only_mode=local_only_mode,
                event_reporting_enabled=event_reporting_enabled,
                show_user_notification=show_user_notification, allow_pause=allow_pause,
                min_extension_version=min_extension_version, policy_version=1,
                rules_data=rules_data, updated_at=_now(),
            )
            self._session.add(record)
        else:
            record.enabled = enabled
            record.trace_match_mode = trace_match_mode
            record.local_only_mode = local_only_mode
            record.event_reporting_enabled = event_reporting_enabled
            record.show_user_notification = show_user_notification
            record.allow_pause = allow_pause
            record.min_extension_version = min_extension_version
            record.rules_data = rules_data
            record.policy_version += 1  # monotonic; sensors reject a regression
            record.updated_at = _now()
        self._session.flush()
        return record

    # -- events -------------------------------------------------------------------------------

    def add_event(
        self, organization_id: UUID, event: MinimizedBrowserEvent, *, correlation_id: str
    ) -> BrowserEventRecord:
        record = BrowserEventRecord(
            organization_id=organization_id,
            browser_sensor_id=UUID(event.browser_sensor_id),
            trace_id=event.trace_id,
            destination_domain=event.destination_domain[:253],
            destination_classification=event.destination_classification.value,
            event_type=event.event_type.value,
            match_method=event.match_method.value,
            confidence=event.confidence,
            extension_version=event.extension_version[:32],
            policy_version=event.policy_version,
            excerpt_hash=event.excerpt_hash,
            minimized_metadata=serialize_metadata(event.minimized_metadata),
            correlation_id=correlation_id,
            observed_at=event.observed_at,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def events_for_org(
        self, organization_id: UUID, *, limit: int = 200
    ) -> tuple[BrowserEventRecord, ...]:
        return tuple(
            self._session.scalars(
                select(BrowserEventRecord)
                .where(BrowserEventRecord.organization_id == organization_id)
                .order_by(BrowserEventRecord.observed_at.desc())
                .limit(limit)
            ).all()
        )

    def events_for_trace(
        self, organization_id: UUID, trace_id: str
    ) -> tuple[BrowserEventRecord, ...]:
        return tuple(
            self._session.scalars(
                select(BrowserEventRecord).where(
                    BrowserEventRecord.organization_id == organization_id,
                    BrowserEventRecord.trace_id == trace_id,
                )
            ).all()
        )

    # -- audit --------------------------------------------------------------------------------

    def add_audit(
        self, *, organization_id: UUID, event_type: str, request_id: str,
        browser_sensor_id: UUID | None = None, actor_id: UUID | None = None,
        safe_metadata: str = "",
    ) -> None:
        self._session.add(
            BrowserSensorAuditRecord(
                organization_id=organization_id, browser_sensor_id=browser_sensor_id,
                actor_id=actor_id, event_type=event_type, request_id=request_id,
                safe_metadata=safe_metadata[:1024],
            )
        )
        self._session.flush()
