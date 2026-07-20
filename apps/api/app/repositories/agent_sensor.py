# Purpose: organization-scoped persistence for agent scope policies, sessions, minimized activity
#   events, scope violations, audit, and the decoy index.
# Responsibilities: policy CRUD (monotonic version), session create/get/list/complete, idempotent
#   event persistence (unique session+external_event_id), violation add/list, bounded timeline, and
#   a bounded org decoy index built from existing tripwire surfaces. Never stores or returns raw
#   content. Dependencies: records, domain, minimize.
from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.domain.agent_sensor import (
    AgentScopePolicyDoc,
    MinimizedAgentEvent,
    ScopeDecision,
)
from app.models.records import (
    AgentActivityEventRecord,
    AgentScopePolicyRecord,
    AgentSensorAuditRecord,
    AgentSessionRecord,
    AiTripwireDeploymentRecord,
    DatabaseHoneyRecordRecord,
    DeploymentTripwireRecord,
    ScopeViolationRecord,
)
from app.services.agent_sensor.decoy import DecoyIndex
from app.services.agent_sensor.minimize import serialize_metadata
from app.services.agent_sensor.paths import normalize_path


def _now() -> datetime:
    return datetime.now(UTC)


class SessionNotFoundError(Exception):
    pass


class PolicyNotFoundError(Exception):
    pass


class AgentSensorRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # -- policies -----------------------------------------------------------------------------

    def create_policy(
        self, organization_id: UUID, doc: AgentScopePolicyDoc
    ) -> AgentScopePolicyRecord:
        record = AgentScopePolicyRecord(
            organization_id=organization_id, name=doc.name[:128],
            allowed_paths=json.dumps(list(doc.allowed_paths)),
            denied_paths=json.dumps(list(doc.denied_paths)),
            allowed_tools=json.dumps(list(doc.allowed_tools)),
            denied_tools=json.dumps(list(doc.denied_tools)),
            allowed_resource_types=json.dumps(list(doc.allowed_resource_types)),
            maximum_file_reads=doc.maximum_file_reads,
            maximum_sensitive_reads=doc.maximum_sensitive_reads,
            allow_dependency_changes=doc.allow_dependency_changes,
            allow_secret_file_access=doc.allow_secret_file_access,
            allow_database_access=doc.allow_database_access,
            allow_network_access=doc.allow_network_access, policy_version=1,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def get_policy(self, organization_id: UUID, policy_id: UUID) -> AgentScopePolicyRecord:
        record = self._session.get(AgentScopePolicyRecord, policy_id)
        if record is None or record.organization_id != organization_id:
            raise PolicyNotFoundError(str(policy_id))
        return record

    def list_policies(self, organization_id: UUID) -> tuple[AgentScopePolicyRecord, ...]:
        return tuple(
            self._session.scalars(
                select(AgentScopePolicyRecord)
                .where(AgentScopePolicyRecord.organization_id == organization_id)
                .order_by(AgentScopePolicyRecord.created_at.desc())
            ).all()
        )

    def update_policy(
        self, record: AgentScopePolicyRecord, doc: AgentScopePolicyDoc
    ) -> AgentScopePolicyRecord:
        record.name = doc.name[:128]
        record.allowed_paths = json.dumps(list(doc.allowed_paths))
        record.denied_paths = json.dumps(list(doc.denied_paths))
        record.allowed_tools = json.dumps(list(doc.allowed_tools))
        record.denied_tools = json.dumps(list(doc.denied_tools))
        record.allowed_resource_types = json.dumps(list(doc.allowed_resource_types))
        record.maximum_file_reads = doc.maximum_file_reads
        record.maximum_sensitive_reads = doc.maximum_sensitive_reads
        record.allow_dependency_changes = doc.allow_dependency_changes
        record.allow_secret_file_access = doc.allow_secret_file_access
        record.allow_database_access = doc.allow_database_access
        record.allow_network_access = doc.allow_network_access
        record.policy_version += 1
        record.updated_at = _now()
        self._session.flush()
        return record

    def delete_policy(self, record: AgentScopePolicyRecord) -> None:
        self._session.delete(record)
        self._session.flush()

    def policy_doc(self, record: AgentScopePolicyRecord) -> AgentScopePolicyDoc:
        return AgentScopePolicyDoc(
            organization_id=str(record.organization_id), name=record.name,
            allowed_paths=tuple(json.loads(record.allowed_paths)),
            denied_paths=tuple(json.loads(record.denied_paths)),
            allowed_tools=tuple(json.loads(record.allowed_tools)),
            denied_tools=tuple(json.loads(record.denied_tools)),
            allowed_resource_types=tuple(json.loads(record.allowed_resource_types)),
            maximum_file_reads=record.maximum_file_reads,
            maximum_sensitive_reads=record.maximum_sensitive_reads,
            allow_dependency_changes=record.allow_dependency_changes,
            allow_secret_file_access=record.allow_secret_file_access,
            allow_database_access=record.allow_database_access,
            allow_network_access=record.allow_network_access,
            policy_version=record.policy_version,
        )

    # -- sessions -----------------------------------------------------------------------------

    def create_session(
        self, *, organization_id: UUID, sensor_id: UUID, external_session_id: str,
        agent_type: str, repository_id: UUID | None, actor_id: UUID | None,
        task_summary: str, scope_policy_id: UUID | None, scope_json: str, correlation_id: str,
    ) -> AgentSessionRecord:
        record = AgentSessionRecord(
            organization_id=organization_id, sensor_id=sensor_id,
            external_session_id=external_session_id[:128], agent_type=agent_type[:48],
            repository_id=repository_id, actor_id=actor_id, status="active",
            task_summary_sanitized=task_summary[:512], scope_policy_id=scope_policy_id,
            scope_data=scope_json, correlation_id=correlation_id,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def get_session(self, organization_id: UUID, session_id: UUID) -> AgentSessionRecord:
        record = self._session.get(AgentSessionRecord, session_id)
        if record is None or record.organization_id != organization_id:
            raise SessionNotFoundError(str(session_id))
        return record

    def find_session_by_external(
        self, organization_id: UUID, external_session_id: str
    ) -> AgentSessionRecord | None:
        return self._session.scalars(
            select(AgentSessionRecord).where(
                AgentSessionRecord.organization_id == organization_id,
                AgentSessionRecord.external_session_id == external_session_id,
            )
        ).first()

    def list_sessions(
        self, organization_id: UUID, *, limit: int = 100
    ) -> tuple[AgentSessionRecord, ...]:
        return tuple(
            self._session.scalars(
                select(AgentSessionRecord)
                .where(AgentSessionRecord.organization_id == organization_id)
                .order_by(AgentSessionRecord.started_at.desc())
                .limit(limit)
            ).all()
        )

    def complete_session(self, record: AgentSessionRecord, *, status: str, summary: str) -> None:
        record.status = status
        record.ended_at = _now()
        record.task_summary_sanitized = record.task_summary_sanitized  # unchanged
        record.scope_data = summary
        record.updated_at = _now()
        self._session.flush()

    # -- events -------------------------------------------------------------------------------

    def add_event(
        self, *, organization_id: UUID, sensor_id: UUID, session_id: UUID,
        event: MinimizedAgentEvent, decision: ScopeDecision, repository_id: UUID | None,
        correlation_id: str,
    ) -> tuple[AgentActivityEventRecord | None, bool]:
        """Persist a minimized event idempotently. Returns (record, created). A duplicate
        external_event_id returns (existing_or_none, False)."""
        record = AgentActivityEventRecord(
            organization_id=organization_id, sensor_id=sensor_id, session_id=session_id,
            external_event_id=event.external_event_id[:128], event_type=event.event_type.value,
            repository_id=repository_id, normalized_path=event.normalized_path,
            path_class=decision.path_class.value, tool_name=event.tool_name,
            resource_type=event.resource_type, resource_id_hash=event.resource_id_hash,
            trace_id=event.trace_id, decoy_id=decision.decoy_id, result_status=event.result_status,
            minimized_metadata=serialize_metadata(event.minimized_metadata),
            correlation_id=correlation_id, observed_at=event.observed_at,
        )
        try:
            with self._session.begin_nested():
                self._session.add(record)
            return record, True
        except IntegrityError:
            return None, False  # duplicate external_event_id -> idempotent no-op

    def events_for_session(
        self, session_id: UUID, *, limit: int = 500
    ) -> tuple[AgentActivityEventRecord, ...]:
        return tuple(
            self._session.scalars(
                select(AgentActivityEventRecord)
                .where(AgentActivityEventRecord.session_id == session_id)
                .order_by(AgentActivityEventRecord.observed_at)
                .limit(limit)
            ).all()
        )

    # -- violations ---------------------------------------------------------------------------

    def add_violation(
        self, *, organization_id: UUID, session_id: UUID, event_id: UUID, decision: ScopeDecision
    ) -> ScopeViolationRecord:
        assert decision.violation_type is not None
        record = ScopeViolationRecord(
            organization_id=organization_id, session_id=session_id, event_id=event_id,
            violation_type=decision.violation_type.value, severity=decision.severity.value,
            confidence=decision.confidence, policy_rule=decision.policy_rule[:128],
            explanation=decision.explanation[:512],
        )
        self._session.add(record)
        self._session.flush()
        return record

    def violations_for_session(self, session_id: UUID) -> tuple[ScopeViolationRecord, ...]:
        return tuple(
            self._session.scalars(
                select(ScopeViolationRecord)
                .where(ScopeViolationRecord.session_id == session_id)
                .order_by(ScopeViolationRecord.created_at)
            ).all()
        )

    # -- decoy index --------------------------------------------------------------------------

    def build_decoy_index(self, organization_id: UUID) -> DecoyIndex:
        index = DecoyIndex()
        for ai in self._session.scalars(
            select(AiTripwireDeploymentRecord).where(
                AiTripwireDeploymentRecord.organization_id == organization_id,
                AiTripwireDeploymentRecord.status == "deployed",
            )
        ).all():
            index.trace_ids[ai.trace_id] = str(ai.id)
        for tw in self._session.scalars(
            select(DeploymentTripwireRecord).where(
                DeploymentTripwireRecord.organization_id == organization_id,
                DeploymentTripwireRecord.status == "active",
            )
        ).all():
            index.trace_ids[tw.trace_identifier] = str(tw.id)
            norm = normalize_path(tw.target_path)
            if norm:
                index.paths[norm.lower()] = str(tw.id)
        for honey in self._session.scalars(
            select(DatabaseHoneyRecordRecord).where(
                DatabaseHoneyRecordRecord.organization_id == organization_id,
                DatabaseHoneyRecordRecord.status == "active",
            )
        ).all():
            index.trace_ids[honey.trace_id] = str(honey.id)
        return index

    # -- audit --------------------------------------------------------------------------------

    def add_audit(
        self, *, organization_id: UUID, event_type: str, request_id: str,
        agent_sensor_id: UUID | None = None, session_id: UUID | None = None,
        actor_id: UUID | None = None, safe_metadata: str = "",
    ) -> None:
        self._session.add(
            AgentSensorAuditRecord(
                organization_id=organization_id, agent_sensor_id=agent_sensor_id,
                session_id=session_id, actor_id=actor_id, event_type=event_type,
                request_id=request_id, safe_metadata=safe_metadata[:1024],
            )
        )
        self._session.flush()
