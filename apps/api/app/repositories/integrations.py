# Purpose: organization-scoped persistence for security integrations, the transactional-outbox
#   deliveries, dead letters, and audit.
# Responsibilities: encrypt integration credentials, resolve them only for the worker, route +
#   create idempotent delivery rows (outbox), claim deliveries with a lease (two workers never share
#   same row), record delivered/retry/dead-letter transitions, and read history. Never returns or
#   logs secrets. Dependencies: records, integrations domain, routing, encryption, settings.
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.models.domain.integrations import SecurityEventEnvelope
from app.models.records import (
    IntegrationAuditRecord,
    IntegrationDeadLetterRecord,
    IntegrationDeliveryRecord,
    SecurityIntegrationRecord,
)
from app.services.encryption import secret_cipher
from app.services.integrations import routing


def _now() -> datetime:
    return datetime.now(UTC)


class IntegrationNotFoundError(Exception):
    pass


class IntegrationRepository:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._cipher = secret_cipher(settings)

    # -- integrations -------------------------------------------------------------------------

    def create_integration(
        self, *, organization_id: UUID, integration_type: str, name: str, endpoint: str,
        secret: str | None, config_json: str, routing_json: str, payload_profile: str,
        minimum_severity: str, include_narrative: bool, include_coverage: bool,
        include_operational: bool, created_by_actor_id: UUID | None,
    ) -> SecurityIntegrationRecord:
        record = SecurityIntegrationRecord(
            organization_id=organization_id, integration_type=integration_type, name=name,
            status="active", endpoint_reference=endpoint,
            secret_ciphertext=self._cipher.encrypt(secret) if secret else None,
            secret_key_version=self._cipher.key_version if secret else None,
            config_data=config_json, routing_data=routing_json, payload_profile=payload_profile,
            minimum_severity=minimum_severity, include_narrative=include_narrative,
            include_coverage_events=include_coverage,
            include_operational_events=include_operational,
            created_by_actor_id=created_by_actor_id,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def get_integration(self, org: UUID, integration_id: UUID) -> SecurityIntegrationRecord:
        record = self._session.get(SecurityIntegrationRecord, integration_id)
        if record is None or record.organization_id != org:
            raise IntegrationNotFoundError(str(integration_id))
        return record

    def list_integrations(self, org: UUID) -> tuple[SecurityIntegrationRecord, ...]:
        return tuple(
            self._session.scalars(
                select(SecurityIntegrationRecord)
                .where(SecurityIntegrationRecord.organization_id == org)
                .order_by(SecurityIntegrationRecord.created_at.desc())
            ).all()
        )

    def resolve_secret(self, record: SecurityIntegrationRecord) -> str | None:
        return self._cipher.decrypt(record.secret_ciphertext) if record.secret_ciphertext else None

    def set_status(
        self, record: SecurityIntegrationRecord, status: str, *, error: str | None = None,
        tested: bool = False, success: bool = False, failure: bool = False,
    ) -> None:
        record.status = status
        record.safe_failure_code = error
        now = _now()
        if tested:
            record.last_tested_at = now
        if success:
            record.last_success_at = now
        if failure:
            record.last_failure_at = now
        record.updated_at = now
        self._session.flush()

    def matching_integrations(
        self, org: UUID, envelope: SecurityEventEnvelope
    ) -> list[SecurityIntegrationRecord]:
        out: list[SecurityIntegrationRecord] = []
        for record in self._session.scalars(
            select(SecurityIntegrationRecord).where(
                SecurityIntegrationRecord.organization_id == org,
                SecurityIntegrationRecord.status == "active",
            )
        ).all():
            if routing.matches(
                routing_json=record.routing_data, minimum_severity=record.minimum_severity,
                include_coverage=record.include_coverage_events,
                include_operational=record.include_operational_events, envelope=envelope,
            ):
                out.append(record)
        return out

    # -- outbox deliveries --------------------------------------------------------------------

    def enqueue_delivery(
        self, *, organization_id: UUID, integration: SecurityIntegrationRecord,
        envelope: SecurityEventEnvelope, event_version: int = 1,
    ) -> IntegrationDeliveryRecord | None:
        """Create one delivery row in the caller's transaction (outbox). Idempotent by key —
        a duplicate source event returns None instead of a second row."""
        key = routing.idempotency_key(
            organization_id=str(organization_id), integration_id=str(integration.id),
            source_id=envelope.source_object_id, event_version=event_version,
            event_type=envelope.event_type.value,
        )
        body = envelope.model_dump_json()
        record = IntegrationDeliveryRecord(
            organization_id=organization_id, integration_id=integration.id,
            source_type=envelope.source_object_type.value, source_id=envelope.source_object_id,
            event_type=envelope.event_type.value, event_version=event_version, idempotency_key=key,
            status="queued", next_attempt_at=_now(), envelope_data=body,
            payload_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
        )
        try:
            with self._session.begin_nested():
                self._session.add(record)
            return record
        except IntegrityError:
            return None  # duplicate logical delivery -> idempotent no-op

    def claim_deliveries(
        self, limit: int, lease_seconds: int
    ) -> tuple[IntegrationDeliveryRecord, ...]:
        """Atomically lease due deliveries. Two workers cannot claim the same row: the update's
        compare-and-set on the lease/status wins for exactly one."""
        now = _now()
        candidates = self._session.scalars(
            select(IntegrationDeliveryRecord.id).where(
                IntegrationDeliveryRecord.status.in_(("queued", "retrying")),
                IntegrationDeliveryRecord.next_attempt_at <= now,
                (IntegrationDeliveryRecord.lease_until.is_(None))
                | (IntegrationDeliveryRecord.lease_until < now),
            ).order_by(IntegrationDeliveryRecord.created_at).limit(limit)
        ).all()
        claimed: list[IntegrationDeliveryRecord] = []
        lease_until = now + timedelta(seconds=lease_seconds)
        for did in candidates:
            result = self._session.execute(
                update(IntegrationDeliveryRecord)
                .where(
                    IntegrationDeliveryRecord.id == did,
                    IntegrationDeliveryRecord.status.in_(("queued", "retrying")),
                    (IntegrationDeliveryRecord.lease_until.is_(None))
                    | (IntegrationDeliveryRecord.lease_until < now),
                )
                .values(status="delivering", lease_until=lease_until)
            )
            if cast("CursorResult[Any]", result).rowcount == 1:
                record = self._session.get(IntegrationDeliveryRecord, did)
                if record is not None:
                    claimed.append(record)
        self._session.flush()
        return tuple(claimed)

    def mark_delivered(self, record: IntegrationDeliveryRecord, *, status_code: int | None) -> None:
        record.status = "delivered"
        record.response_status = status_code
        record.attempt_count += 1
        record.lease_until = None
        record.delivered_at = _now()
        record.updated_at = _now()
        record.safe_error_code = None
        self._session.flush()

    def mark_retry(
        self, record: IntegrationDeliveryRecord, *, delay_seconds: float, error: str | None,
        status_code: int | None,
    ) -> None:
        record.status = "retrying"
        record.attempt_count += 1
        record.next_attempt_at = _now() + timedelta(seconds=delay_seconds)
        record.lease_until = None
        record.response_status = status_code
        record.safe_error_code = error
        record.updated_at = _now()
        self._session.flush()

    def mark_dead_letter(
        self, record: IntegrationDeliveryRecord, *, reason: str, status_code: int | None,
    ) -> None:
        record.status = "dead_lettered"
        record.attempt_count += 1
        record.lease_until = None
        record.response_status = status_code
        record.safe_error_code = reason
        record.updated_at = _now()
        self._session.add(IntegrationDeadLetterRecord(
            organization_id=record.organization_id, integration_id=record.integration_id,
            delivery_id=record.id, reason_code=reason[:64], first_failed_at=record.created_at,
            final_failed_at=_now(), attempt_count=record.attempt_count,
            payload_hash=record.payload_hash,
        ))
        self._session.flush()

    def get_delivery(self, org: UUID, delivery_id: UUID) -> IntegrationDeliveryRecord | None:
        record = self._session.get(IntegrationDeliveryRecord, delivery_id)
        if record is None or record.organization_id != org:
            return None
        return record

    def list_deliveries(
        self, org: UUID, *, limit: int = 100
    ) -> tuple[IntegrationDeliveryRecord, ...]:
        return tuple(
            self._session.scalars(
                select(IntegrationDeliveryRecord)
                .where(IntegrationDeliveryRecord.organization_id == org)
                .order_by(IntegrationDeliveryRecord.created_at.desc())
                .limit(limit)
            ).all()
        )

    def dead_letters(self, org: UUID) -> tuple[IntegrationDeadLetterRecord, ...]:
        return tuple(
            self._session.scalars(
                select(IntegrationDeadLetterRecord)
                .where(IntegrationDeadLetterRecord.organization_id == org)
                .order_by(IntegrationDeadLetterRecord.created_at.desc())
            ).all()
        )

    def requeue_delivery(self, record: IntegrationDeliveryRecord) -> None:
        record.status = "queued"
        record.next_attempt_at = _now()
        record.lease_until = None
        record.updated_at = _now()
        self._session.flush()

    # -- audit --------------------------------------------------------------------------------

    def add_audit(
        self, *, organization_id: UUID, event_type: str, request_id: str,
        integration_id: UUID | None = None, delivery_id: UUID | None = None,
        actor_id: UUID | None = None, safe_metadata: str = "",
    ) -> None:
        self._session.add(IntegrationAuditRecord(
            organization_id=organization_id, integration_id=integration_id, delivery_id=delivery_id,
            actor_id=actor_id, event_type=event_type, request_id=request_id,
            safe_metadata=safe_metadata[:1024],
        ))
        self._session.flush()
