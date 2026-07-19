# Purpose: organization-scoped persistence for AI (RAG/MCP) connectors, tripwire deployments,
#   minimized events, jobs, and audit.
# Responsibilities: encrypt connector secrets at rest, apply state-machine-checked transitions,
#   dedup jobs, claim atomically, and store only minimized events (never prompts/chunks/outputs).
#   Never returns or logs secrets or raw content. Dependencies: records, domain, encryption.
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.models.domain.ai_tripwire import (
    AiTripwirePreview,
    AiTripwireStatus,
    MinimizedAiEvent,
    assert_transition,
)
from app.models.records import (
    AiTripwireAuditRecord,
    AiTripwireDeploymentRecord,
    AiTripwireEventRecord,
    AiTripwireJobRecord,
    McpConnectorRecord,
    RagConnectorRecord,
)
from app.services.ai_tripwire.minimize import serialize_metadata
from app.services.encryption import secret_cipher


def _now() -> datetime:
    return datetime.now(UTC)


class ConnectorNotFoundError(Exception):
    pass


class DeploymentNotFoundError(Exception):
    pass


class AiTripwireRepository:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._cipher = secret_cipher(settings)

    # -- connectors ---------------------------------------------------------------------------

    def create_rag_connector(
        self, *, organization_id: UUID, connector_type: str, name: str, secret: str,
        index_or_collection: str, namespace: str | None, created_by_actor_id: UUID | None,
    ) -> RagConnectorRecord:
        record = RagConnectorRecord(
            organization_id=organization_id, connector_type=connector_type, name=name,
            secret_ciphertext=self._cipher.encrypt(secret),
            secret_key_version=self._cipher.key_version,
            index_or_collection=index_or_collection, namespace=namespace, status="pending",
            created_by_actor_id=created_by_actor_id,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def create_mcp_connector(
        self, *, organization_id: UUID, name: str, server_reference: str, transport_type: str,
        secret: str | None, created_by_actor_id: UUID | None,
    ) -> McpConnectorRecord:
        record = McpConnectorRecord(
            organization_id=organization_id, name=name, server_reference=server_reference,
            transport_type=transport_type,
            secret_ciphertext=self._cipher.encrypt(secret) if secret else None,
            secret_key_version=self._cipher.key_version if secret else None,
            status="pending", created_by_actor_id=created_by_actor_id,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def get_rag_connector(self, org: UUID, connector_id: UUID) -> RagConnectorRecord:
        record = self._session.get(RagConnectorRecord, connector_id)
        if record is None or record.organization_id != org:
            raise ConnectorNotFoundError(str(connector_id))
        return record

    def get_mcp_connector(self, org: UUID, connector_id: UUID) -> McpConnectorRecord:
        record = self._session.get(McpConnectorRecord, connector_id)
        if record is None or record.organization_id != org:
            raise ConnectorNotFoundError(str(connector_id))
        return record

    def resolve_secret(self, ciphertext: str | None) -> str | None:
        return self._cipher.decrypt(ciphertext) if ciphertext else None

    def list_rag_connectors(self, org: UUID) -> tuple[RagConnectorRecord, ...]:
        return tuple(
            self._session.scalars(
                select(RagConnectorRecord).where(RagConnectorRecord.organization_id == org)
                .order_by(RagConnectorRecord.created_at.desc())
            ).all()
        )

    def list_mcp_connectors(self, org: UUID) -> tuple[McpConnectorRecord, ...]:
        return tuple(
            self._session.scalars(
                select(McpConnectorRecord).where(McpConnectorRecord.organization_id == org)
                .order_by(McpConnectorRecord.created_at.desc())
            ).all()
        )

    def set_rag_status(self, record: RagConnectorRecord, status: str, *, error: str | None = None,
                       tested: bool = False) -> None:
        record.status = status
        record.safe_error_code = error
        if tested:
            record.last_tested_at = _now()
        record.updated_at = _now()
        self._session.flush()

    def set_mcp_status(self, record: McpConnectorRecord, status: str, *, error: str | None = None,
                       tested: bool = False) -> None:
        record.status = status
        record.safe_error_code = error
        if tested:
            record.last_tested_at = _now()
        record.updated_at = _now()
        self._session.flush()

    # -- deployments --------------------------------------------------------------------------

    def create_deployment(
        self, *, organization_id: UUID, surface_type: str, connector_id: UUID,
        target_collection: str, decoy_kind: str, trace_id: str,
        requested_by_actor_id: UUID | None, expires_at: datetime | None,
    ) -> AiTripwireDeploymentRecord:
        record = AiTripwireDeploymentRecord(
            organization_id=organization_id, surface_type=surface_type, connector_id=connector_id,
            target_collection=target_collection, decoy_kind=decoy_kind,
            status=AiTripwireStatus.DRAFT.value, trace_id=trace_id,
            requested_by_actor_id=requested_by_actor_id, expires_at=expires_at,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def get_deployment(self, org: UUID, deployment_id: UUID) -> AiTripwireDeploymentRecord:
        record = self._session.get(AiTripwireDeploymentRecord, deployment_id)
        if record is None or record.organization_id != org:
            raise DeploymentNotFoundError(str(deployment_id))
        return record

    def list_deployments(self, org: UUID) -> tuple[AiTripwireDeploymentRecord, ...]:
        return tuple(
            self._session.scalars(
                select(AiTripwireDeploymentRecord)
                .where(AiTripwireDeploymentRecord.organization_id == org)
                .order_by(AiTripwireDeploymentRecord.created_at.desc())
            ).all()
        )

    def find_by_trace(self, org: UUID, trace_id: str) -> AiTripwireDeploymentRecord | None:
        return self._session.scalars(
            select(AiTripwireDeploymentRecord).where(
                AiTripwireDeploymentRecord.organization_id == org,
                AiTripwireDeploymentRecord.trace_id == trace_id,
            )
        ).first()

    def set_preview(self, record: AiTripwireDeploymentRecord, preview: AiTripwirePreview) -> None:
        record.preview_hash = preview.preview_hash
        record.preview_data = preview.model_dump_json()
        record.updated_at = _now()
        self._session.flush()

    def load_preview(self, record: AiTripwireDeploymentRecord) -> AiTripwirePreview | None:
        if record.preview_data is None:
            return None
        return AiTripwirePreview.model_validate_json(record.preview_data)

    def transition(
        self, record: AiTripwireDeploymentRecord, target: AiTripwireStatus, **fields: Any
    ) -> None:
        assert_transition(AiTripwireStatus(record.status), target)
        record.status = target.value
        for key, value in fields.items():
            setattr(record, key, value)
        record.updated_at = _now()
        self._session.flush()

    # -- events -------------------------------------------------------------------------------

    def add_event(self, organization_id: UUID, event: MinimizedAiEvent) -> AiTripwireEventRecord:
        record = AiTripwireEventRecord(
            organization_id=organization_id,
            deployment_id=UUID(event.deployment_id),
            trace_id=event.trace_id,
            surface_type=event.surface_type.value,
            event_type=event.event_type.value,
            source_id=event.source_id[:256],
            monitor_identity=event.monitor_identity[:128],
            confidence=event.confidence,
            minimized_metadata=serialize_metadata(event.minimized_metadata),
            observed_at=event.observed_at,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def events_for(self, deployment_id: UUID) -> tuple[AiTripwireEventRecord, ...]:
        return tuple(
            self._session.scalars(
                select(AiTripwireEventRecord).where(
                    AiTripwireEventRecord.deployment_id == deployment_id
                ).order_by(AiTripwireEventRecord.observed_at)
            ).all()
        )

    # -- job queue ----------------------------------------------------------------------------

    def enqueue_job(
        self, *, organization_id: UUID, deployment_id: UUID, job_type: str, correlation_id: str
    ) -> bool:
        try:
            with self._session.begin_nested():
                self._session.add(
                    AiTripwireJobRecord(
                        organization_id=organization_id, deployment_id=deployment_id,
                        job_type=job_type, status="pending", correlation_id=correlation_id,
                    )
                )
            return True
        except IntegrityError:
            return False

    def clear_job(self, deployment_id: UUID, job_type: str) -> None:
        for record in self._session.scalars(
            select(AiTripwireJobRecord).where(
                AiTripwireJobRecord.deployment_id == deployment_id,
                AiTripwireJobRecord.job_type == job_type,
            )
        ).all():
            self._session.delete(record)
        self._session.flush()

    def claim_jobs(self, limit: int) -> tuple[AiTripwireJobRecord, ...]:
        candidate_ids = self._session.scalars(
            select(AiTripwireJobRecord.id).where(AiTripwireJobRecord.status == "pending")
            .order_by(AiTripwireJobRecord.created_at).limit(limit)
        ).all()
        claimed: list[AiTripwireJobRecord] = []
        for job_id in candidate_ids:
            result = self._session.execute(
                update(AiTripwireJobRecord)
                .where(AiTripwireJobRecord.id == job_id, AiTripwireJobRecord.status == "pending")
                .values(status="claimed")
            )
            if cast("CursorResult[Any]", result).rowcount == 1:
                record = self._session.get(AiTripwireJobRecord, job_id)
                if record is not None:
                    record.attempts += 1
                    claimed.append(record)
        self._session.flush()
        return tuple(claimed)

    def complete_job(self, job_id: UUID, *, ok: bool) -> None:
        record = self._session.get(AiTripwireJobRecord, job_id)
        if record is None:
            return
        record.status = "done" if ok else "failed"
        record.processed_at = _now()
        self._session.flush()

    # -- audit --------------------------------------------------------------------------------

    def add_audit(
        self, *, organization_id: UUID, event_type: str, request_id: str,
        deployment_id: UUID | None = None, connector_id: UUID | None = None,
        actor_id: UUID | None = None, safe_metadata: str = "",
    ) -> None:
        self._session.add(
            AiTripwireAuditRecord(
                organization_id=organization_id, deployment_id=deployment_id,
                connector_id=connector_id, actor_id=actor_id, event_type=event_type,
                request_id=request_id, safe_metadata=safe_metadata[:1024],
            )
        )
        self._session.flush()

    def audit_events(self, deployment_id: UUID) -> tuple[AiTripwireAuditRecord, ...]:
        return tuple(
            self._session.scalars(
                select(AiTripwireAuditRecord)
                .where(AiTripwireAuditRecord.deployment_id == deployment_id)
                .order_by(AiTripwireAuditRecord.created_at)
            ).all()
        )


def new_correlation_id() -> str:
    return uuid4().hex
