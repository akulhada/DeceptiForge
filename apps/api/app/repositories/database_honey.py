# Purpose: organization-scoped persistence for database connectors, schema snapshots, honey
#   deployments, inserted records, jobs, and audit.
# Responsibilities: enforce org scoping on every read/write, encrypt connector secrets and inserted
#   values at rest, apply state-machine-checked transitions, dedup jobs, claim atomically, and
#   activate records idempotently. Never returns or logs secrets. Dependencies: records, domain,
#   encryption, settings.
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.models.domain.database_honey import (
    HoneyDeploymentPreview,
    HoneyDeploymentStatus,
    SchemaSnapshot,
    assert_transition,
)
from app.models.records import (
    DatabaseConnectorRecord,
    DatabaseHoneyAuditRecord,
    DatabaseHoneyDeploymentRecord,
    DatabaseHoneyJobRecord,
    DatabaseHoneyRecordRecord,
    DatabaseSchemaSnapshotRecord,
)
from app.services.encryption import secret_cipher


def _now() -> datetime:
    return datetime.now(UTC)


class ConnectorNotFoundError(Exception):
    pass


class HoneyDeploymentNotFoundError(Exception):
    pass


class DatabaseHoneyRepository:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._cipher = secret_cipher(settings)

    # -- connectors ---------------------------------------------------------------------------

    def create_connector(
        self,
        *,
        organization_id: UUID,
        name: str,
        host_reference: str,
        database_name: str,
        secret_payload: dict[str, Any],
        ssl_mode: str,
        read_only_mode: bool,
        created_by_actor_id: UUID | None,
    ) -> DatabaseConnectorRecord:
        record = DatabaseConnectorRecord(
            organization_id=organization_id,
            name=name,
            host_reference=host_reference,
            database_name=database_name,
            secret_ciphertext=self._cipher.encrypt(json.dumps(secret_payload)),
            secret_key_version=self._cipher.key_version,
            ssl_mode=ssl_mode,
            status="pending",
            read_only_mode=read_only_mode,
            created_by_actor_id=created_by_actor_id,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def get_connector(self, organization_id: UUID, connector_id: UUID) -> DatabaseConnectorRecord:
        record = self._session.get(DatabaseConnectorRecord, connector_id)
        if record is None or record.organization_id != organization_id:
            raise ConnectorNotFoundError(str(connector_id))
        return record

    def resolve_secret(self, record: DatabaseConnectorRecord) -> dict[str, Any]:
        """Decrypt the connector credential for in-memory use only. Never persist/log the result."""
        return cast(dict[str, Any], json.loads(self._cipher.decrypt(record.secret_ciphertext)))

    def list_connectors(self, organization_id: UUID) -> tuple[DatabaseConnectorRecord, ...]:
        rows = self._session.scalars(
            select(DatabaseConnectorRecord)
            .where(DatabaseConnectorRecord.organization_id == organization_id)
            .order_by(DatabaseConnectorRecord.created_at.desc())
        ).all()
        return tuple(rows)

    def set_connector_status(
        self, record: DatabaseConnectorRecord, status: str, *, error_code: str | None = None,
        tested: bool = False, schema_synced: bool = False,
    ) -> None:
        record.status = status
        record.safe_error_code = error_code
        if tested:
            record.last_tested_at = _now()
        if schema_synced:
            record.last_schema_sync_at = _now()
        record.updated_at = _now()
        self._session.flush()

    def delete_connector(self, record: DatabaseConnectorRecord) -> None:
        record.status = "revoked"
        record.updated_at = _now()
        self._session.flush()

    # -- schema snapshots ---------------------------------------------------------------------

    def add_snapshot(
        self, organization_id: UUID, connector_id: UUID, snapshot: SchemaSnapshot
    ) -> DatabaseSchemaSnapshotRecord:
        record = DatabaseSchemaSnapshotRecord(
            organization_id=organization_id,
            connector_id=connector_id,
            captured_at=_now(),
            database_version=snapshot.database_version,
            snapshot_hash=snapshot.snapshot_hash,
            data=snapshot.model_dump_json(),
        )
        self._session.add(record)
        self._session.flush()
        return record

    def get_snapshot(self, organization_id: UUID, snapshot_id: UUID) -> SchemaSnapshot:
        record = self._session.get(DatabaseSchemaSnapshotRecord, snapshot_id)
        if record is None or record.organization_id != organization_id:
            raise HoneyDeploymentNotFoundError("snapshot not found")
        return SchemaSnapshot.model_validate_json(record.data)

    def latest_snapshot(
        self, organization_id: UUID, connector_id: UUID
    ) -> DatabaseSchemaSnapshotRecord | None:
        return self._session.scalars(
            select(DatabaseSchemaSnapshotRecord)
            .where(
                DatabaseSchemaSnapshotRecord.organization_id == organization_id,
                DatabaseSchemaSnapshotRecord.connector_id == connector_id,
            )
            .order_by(DatabaseSchemaSnapshotRecord.captured_at.desc())
        ).first()

    # -- deployments --------------------------------------------------------------------------

    def create_deployment(
        self,
        *,
        organization_id: UUID,
        connector_id: UUID,
        schema_snapshot_id: UUID,
        target_schema: str,
        target_table: str,
        decoy_type: str,
        requested_by_actor_id: UUID | None,
        expires_at: datetime | None,
    ) -> DatabaseHoneyDeploymentRecord:
        record = DatabaseHoneyDeploymentRecord(
            organization_id=organization_id,
            connector_id=connector_id,
            schema_snapshot_id=schema_snapshot_id,
            target_schema=target_schema,
            target_table=target_table,
            decoy_type=decoy_type,
            status=HoneyDeploymentStatus.DRAFT.value,
            requested_by_actor_id=requested_by_actor_id,
            expires_at=expires_at,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def get_deployment(
        self, organization_id: UUID, deployment_id: UUID
    ) -> DatabaseHoneyDeploymentRecord:
        record = self._session.get(DatabaseHoneyDeploymentRecord, deployment_id)
        if record is None or record.organization_id != organization_id:
            raise HoneyDeploymentNotFoundError(str(deployment_id))
        return record

    def list_deployments(
        self, organization_id: UUID
    ) -> tuple[DatabaseHoneyDeploymentRecord, ...]:
        rows = self._session.scalars(
            select(DatabaseHoneyDeploymentRecord)
            .where(DatabaseHoneyDeploymentRecord.organization_id == organization_id)
            .order_by(DatabaseHoneyDeploymentRecord.created_at.desc())
        ).all()
        return tuple(rows)

    def set_preview(
        self, record: DatabaseHoneyDeploymentRecord, preview: HoneyDeploymentPreview
    ) -> None:
        record.preview_hash = preview.preview_hash
        record.preview_data = preview.model_dump_json()
        record.updated_at = _now()
        self._session.flush()

    def load_preview(
        self, record: DatabaseHoneyDeploymentRecord
    ) -> HoneyDeploymentPreview | None:
        if record.preview_data is None:
            return None
        return HoneyDeploymentPreview.model_validate_json(record.preview_data)

    def transition(
        self, record: DatabaseHoneyDeploymentRecord, target: HoneyDeploymentStatus, **fields: Any
    ) -> None:
        assert_transition(HoneyDeploymentStatus(record.status), target)
        record.status = target.value
        for key, value in fields.items():
            setattr(record, key, value)
        record.updated_at = _now()
        self._session.flush()

    # -- honey records ------------------------------------------------------------------------

    def record_exists(self, deployment_id: UUID, row_fingerprint: str) -> bool:
        return (
            self._session.scalars(
                select(DatabaseHoneyRecordRecord).where(
                    DatabaseHoneyRecordRecord.deployment_id == deployment_id,
                    DatabaseHoneyRecordRecord.row_fingerprint == row_fingerprint,
                )
            ).first()
            is not None
        )

    def add_record(
        self,
        *,
        organization_id: UUID,
        deployment_id: UUID,
        trace_id: str,
        primary_key: dict[str, Any],
        row_fingerprint: str,
        inserted_values: dict[str, Any],
        verification_hash: str,
    ) -> bool:
        """Persist an inserted honey record idempotently; return False if the fingerprint exists."""
        try:
            with self._session.begin_nested():
                self._session.add(
                    DatabaseHoneyRecordRecord(
                        organization_id=organization_id,
                        deployment_id=deployment_id,
                        trace_id=trace_id,
                        target_primary_key=json.dumps(primary_key, default=str),
                        row_fingerprint=row_fingerprint,
                        inserted_values_encrypted=self._cipher.encrypt(
                            json.dumps(inserted_values, default=str)
                        ),
                        verification_hash=verification_hash,
                        status="inserted",
                        inserted_at=_now(),
                    )
                )
            return True
        except IntegrityError:
            return False

    def records_for(self, deployment_id: UUID) -> tuple[DatabaseHoneyRecordRecord, ...]:
        rows = self._session.scalars(
            select(DatabaseHoneyRecordRecord).where(
                DatabaseHoneyRecordRecord.deployment_id == deployment_id
            )
        ).all()
        return tuple(rows)

    def decrypt_values(self, record: DatabaseHoneyRecordRecord) -> dict[str, Any]:
        raw = self._cipher.decrypt(record.inserted_values_encrypted)
        return cast(dict[str, Any], json.loads(raw))

    def set_record_status(self, record: DatabaseHoneyRecordRecord, status: str) -> None:
        record.status = status
        if status == "retired":
            record.retired_at = _now()
        self._session.flush()

    def active_record_count(self, deployment_id: UUID) -> int:
        return len(
            self._session.scalars(
                select(DatabaseHoneyRecordRecord).where(
                    DatabaseHoneyRecordRecord.deployment_id == deployment_id,
                    DatabaseHoneyRecordRecord.status == "inserted",
                )
            ).all()
        )

    # -- job queue ----------------------------------------------------------------------------

    def enqueue_job(
        self, *, organization_id: UUID, deployment_id: UUID, job_type: str, correlation_id: str
    ) -> bool:
        try:
            with self._session.begin_nested():
                self._session.add(
                    DatabaseHoneyJobRecord(
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

    def clear_job(self, deployment_id: UUID, job_type: str) -> None:
        for record in self._session.scalars(
            select(DatabaseHoneyJobRecord).where(
                DatabaseHoneyJobRecord.deployment_id == deployment_id,
                DatabaseHoneyJobRecord.job_type == job_type,
            )
        ).all():
            self._session.delete(record)
        self._session.flush()

    def claim_jobs(self, limit: int) -> tuple[DatabaseHoneyJobRecord, ...]:
        candidate_ids = self._session.scalars(
            select(DatabaseHoneyJobRecord.id)
            .where(DatabaseHoneyJobRecord.status == "pending")
            .order_by(DatabaseHoneyJobRecord.created_at)
            .limit(limit)
        ).all()
        claimed: list[DatabaseHoneyJobRecord] = []
        for job_id in candidate_ids:
            result = self._session.execute(
                update(DatabaseHoneyJobRecord)
                .where(
                    DatabaseHoneyJobRecord.id == job_id,
                    DatabaseHoneyJobRecord.status == "pending",
                )
                .values(status="claimed")
            )
            if cast("CursorResult[Any]", result).rowcount == 1:
                record = self._session.get(DatabaseHoneyJobRecord, job_id)
                if record is not None:
                    record.attempts += 1
                    claimed.append(record)
        self._session.flush()
        return tuple(claimed)

    def complete_job(self, job_id: UUID, *, ok: bool) -> None:
        record = self._session.get(DatabaseHoneyJobRecord, job_id)
        if record is None:
            return
        record.status = "done" if ok else "failed"
        record.processed_at = _now()
        self._session.flush()

    # -- audit --------------------------------------------------------------------------------

    def add_audit(
        self,
        *,
        organization_id: UUID,
        event_type: str,
        request_id: str,
        deployment_id: UUID | None = None,
        connector_id: UUID | None = None,
        actor_id: UUID | None = None,
        safe_metadata: str = "",
    ) -> None:
        self._session.add(
            DatabaseHoneyAuditRecord(
                organization_id=organization_id,
                deployment_id=deployment_id,
                connector_id=connector_id,
                actor_id=actor_id,
                event_type=event_type,
                request_id=request_id,
                safe_metadata=safe_metadata[:1024],
            )
        )
        self._session.flush()

    def audit_events(self, deployment_id: UUID) -> tuple[DatabaseHoneyAuditRecord, ...]:
        rows = self._session.scalars(
            select(DatabaseHoneyAuditRecord)
            .where(DatabaseHoneyAuditRecord.deployment_id == deployment_id)
            .order_by(DatabaseHoneyAuditRecord.created_at)
        ).all()
        return tuple(rows)


def new_correlation_id() -> str:
    return uuid4().hex
