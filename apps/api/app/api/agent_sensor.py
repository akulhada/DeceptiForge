# Purpose: HTTP surface for AI agent activity sensors — enrollment, sessions, scope policies, the
#   scoped decoy-aware timeline, and trusted signed minimized activity-event ingestion.
# Responsibilities: enrollment token creation (admin) + one-time enroll (token-authenticated),
#   sensor list/revoke, session create/list/get/complete, policy CRUD (monotonic version), signed +
#   replay-protected + minimized + idempotent event ingestion with deterministic scope-violation
#   evaluation, and session violations/timeline. Detect-only. Secrets shown once. Org + scope bound.
# Dependencies: services, repository, monitor signing/replay, settings, auth.
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.dependencies import get_db
from app.models.domain.agent_sensor import (
    AgentEventType,
    AgentScopePolicyDoc,
    MinimizedAgentEvent,
    PathClass,
)
from app.repositories.agent_sensor import (
    AgentSensorRepository,
    PolicyNotFoundError,
    SessionNotFoundError,
)
from app.security import require_scope
from app.services.agent_sensor.classification import exposure_for, incident_severity
from app.services.agent_sensor.decoy import resolve_decoy
from app.services.agent_sensor.minimize import minimize_metadata
from app.services.agent_sensor.paths import normalize_path
from app.services.agent_sensor.rules import SessionAggregate, evaluate
from app.services.agent_sensor.scope import normalize_scope
from app.services.agent_sensor.sequence import detect_escalation, session_summary
from app.services.agent_sensor.service import (
    AgentSensorService,
    EnrollmentError,
    SensorSignatureError,
)
from app.services.api_keys import AuthContext
from app.services.metrics import emit
from app.services.replay import ReplayError, get_replay_guard

router = APIRouter(tags=["agent-sensors"])


# ---- schemas -------------------------------------------------------------------------------------


class EnrollmentTokenResponse(BaseModel):
    token: str
    expires_at: datetime


class EnrollRequest(BaseModel):
    token: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    adapter_type: str = Field(min_length=1, max_length=48)
    version: str = Field(min_length=1, max_length=32)


class EnrollResponse(BaseModel):
    sensor_id: UUID
    sensor_public_id: str
    organization_id: UUID
    signing_secret: str
    api_key: str


class SensorSummary(BaseModel):
    id: UUID
    sensor_public_id: str
    name: str
    adapter_type: str
    version: str
    status: str
    last_seen_at: datetime | None
    created_at: datetime


class PolicyBody(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    allowed_paths: list[str] = Field(default_factory=list, max_length=500)
    denied_paths: list[str] = Field(default_factory=list, max_length=500)
    allowed_tools: list[str] = Field(default_factory=list, max_length=200)
    denied_tools: list[str] = Field(default_factory=list, max_length=200)
    allowed_resource_types: list[str] = Field(default_factory=list, max_length=100)
    maximum_file_reads: int = Field(default=200, ge=0, le=100000)
    maximum_sensitive_reads: int = Field(default=0, ge=0, le=100000)
    allow_dependency_changes: bool = False
    allow_secret_file_access: bool = False
    allow_database_access: bool = False
    allow_network_access: bool = False


class PolicySummary(BaseModel):
    id: UUID
    name: str
    policy_version: int
    allowed_paths: list[str]
    denied_paths: list[str]
    maximum_file_reads: int
    maximum_sensitive_reads: int
    allow_database_access: bool
    allow_network_access: bool
    created_at: datetime
    updated_at: datetime


class CreateSessionRequest(BaseModel):
    external_session_id: str = Field(min_length=1, max_length=128)
    agent_type: str = Field(min_length=1, max_length=48)
    task_summary: str = Field(default="", max_length=4000)
    repository_id: UUID | None = None
    scope_policy_id: UUID | None = None
    allowed_paths: list[str] = Field(default_factory=list, max_length=500)
    denied_paths: list[str] = Field(default_factory=list, max_length=500)


class SessionSummary(BaseModel):
    id: UUID
    sensor_id: UUID
    external_session_id: str
    agent_type: str
    status: str
    task_summary_sanitized: str
    scope_policy_id: UUID | None
    correlation_id: str
    started_at: datetime
    ended_at: datetime | None


class AgentEventRequest(BaseModel):
    external_event_id: str = Field(min_length=1, max_length=128)
    session_external_id: str = Field(min_length=1, max_length=128)
    event_type: str
    path: str | None = Field(default=None, max_length=4096)
    tool_name: str | None = Field(default=None, max_length=128)
    resource_type: str | None = Field(default=None, max_length=64)
    resource_id_hash: str | None = Field(default=None, max_length=128)
    trace_id: str | None = Field(default=None, max_length=128)
    result_status: str = Field(default="ok", max_length=32)
    metadata: dict[str, str] = Field(default_factory=dict)
    observed_at: datetime | None = None


class AgentEventResponse(BaseModel):
    accepted: bool
    idempotent: bool
    path_class: str
    violation_type: str | None
    severity: str
    explanation: str


def _sensor_summary(r) -> SensorSummary:  # type: ignore[no-untyped-def]
    return SensorSummary(
        id=r.id, sensor_public_id=r.sensor_public_id, name=r.name, adapter_type=r.adapter_type,
        version=r.version, status=r.status, last_seen_at=r.last_seen_at, created_at=r.created_at,
    )


def _policy_summary(r) -> PolicySummary:  # type: ignore[no-untyped-def]
    import json

    return PolicySummary(
        id=r.id, name=r.name, policy_version=r.policy_version,
        allowed_paths=json.loads(r.allowed_paths), denied_paths=json.loads(r.denied_paths),
        maximum_file_reads=r.maximum_file_reads, maximum_sensitive_reads=r.maximum_sensitive_reads,
        allow_database_access=r.allow_database_access, allow_network_access=r.allow_network_access,
        created_at=r.created_at, updated_at=r.updated_at,
    )


def _session_summary(r) -> SessionSummary:  # type: ignore[no-untyped-def]
    return SessionSummary(
        id=r.id, sensor_id=r.sensor_id, external_session_id=r.external_session_id,
        agent_type=r.agent_type, status=r.status,
        task_summary_sanitized=r.task_summary_sanitized, scope_policy_id=r.scope_policy_id,
        correlation_id=r.correlation_id, started_at=r.started_at, ended_at=r.ended_at,
    )


# ---- helpers -------------------------------------------------------------------------------------


def _require_enabled(settings: Settings) -> None:
    if not settings.agent_sensor_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent sensors are not enabled")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


async def _raw_body(request: Request) -> bytes:
    return await request.body()


def _policy_doc(body: PolicyBody, org: str, settings: Settings) -> AgentScopePolicyDoc:
    return AgentScopePolicyDoc(
        organization_id=org, name=body.name,
        allowed_paths=tuple(body.allowed_paths[: settings.agent_scope_max_allowed_paths]),
        denied_paths=tuple(body.denied_paths[: settings.agent_scope_max_denied_paths]),
        allowed_tools=tuple(body.allowed_tools), denied_tools=tuple(body.denied_tools),
        allowed_resource_types=tuple(body.allowed_resource_types),
        maximum_file_reads=body.maximum_file_reads,
        maximum_sensitive_reads=body.maximum_sensitive_reads,
        allow_dependency_changes=body.allow_dependency_changes,
        allow_secret_file_access=body.allow_secret_file_access,
        allow_database_access=body.allow_database_access,
        allow_network_access=body.allow_network_access,
    )


# ---- enrollment + sensors ------------------------------------------------------------------------


@router.post(
    "/agent-sensors/enrollment-tokens", response_model=EnrollmentTokenResponse, status_code=201
)
def create_enrollment_token(
    request: Request,
    auth: AuthContext = Depends(require_scope("agent_sensors:manage")),
    session: Session = Depends(get_db),
) -> EnrollmentTokenResponse:
    settings = get_settings()
    _require_enabled(settings)
    record, token = AgentSensorService(session, settings).create_enrollment_token(
        auth.organization_id, created_by_actor_id=auth.key_id
    )
    AgentSensorRepository(session).add_audit(
        organization_id=auth.organization_id, actor_id=auth.key_id,
        event_type="enrollment_token_created", request_id=_request_id(request),
    )
    return EnrollmentTokenResponse(token=token, expires_at=record.expires_at)


@router.post("/agent-sensors/enroll", response_model=EnrollResponse, status_code=201)
def enroll(
    body: EnrollRequest, request: Request, session: Session = Depends(get_db)
) -> EnrollResponse:
    settings = get_settings()
    _require_enabled(settings)
    try:
        result = AgentSensorService(session, settings).enroll(
            token=body.token, name=body.name, adapter_type=body.adapter_type, version=body.version
        )
    except EnrollmentError as error:
        raise HTTPException(error.status_code, error.message) from None
    AgentSensorRepository(session).add_audit(
        organization_id=result.sensor.organization_id, agent_sensor_id=result.sensor.id,
        event_type="sensor_enrolled", request_id=_request_id(request),
        safe_metadata=result.sensor_public_id,
    )
    return EnrollResponse(
        sensor_id=result.sensor.id, sensor_public_id=result.sensor_public_id,
        organization_id=result.sensor.organization_id, signing_secret=result.signing_secret,
        api_key=result.api_key,
    )


@router.get("/agent-sensors", response_model=list[SensorSummary])
def list_sensors(
    auth: AuthContext = Depends(require_scope("agent_sensors:read")),
    session: Session = Depends(get_db),
) -> list[SensorSummary]:
    settings = get_settings()
    _require_enabled(settings)
    rows = AgentSensorService(session, settings).list(auth.organization_id)
    return [_sensor_summary(r) for r in rows]


@router.post("/agent-sensors/{sensor_id}/revoke", response_model=SensorSummary)
def revoke_sensor(
    sensor_id: UUID, request: Request,
    auth: AuthContext = Depends(require_scope("agent_sensors:manage")),
    session: Session = Depends(get_db),
) -> SensorSummary:
    settings = get_settings()
    _require_enabled(settings)
    svc = AgentSensorService(session, settings)
    record = svc.get(auth.organization_id, sensor_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sensor not found")
    svc.revoke(record)
    AgentSensorRepository(session).add_audit(
        organization_id=auth.organization_id, agent_sensor_id=sensor_id, actor_id=auth.key_id,
        event_type="sensor_revoked", request_id=_request_id(request),
    )
    return _sensor_summary(record)


# ---- policies ------------------------------------------------------------------------------------


@router.get("/agent-scope-policies", response_model=list[PolicySummary])
def list_policies(
    auth: AuthContext = Depends(require_scope("agent_policies:read")),
    session: Session = Depends(get_db),
) -> list[PolicySummary]:
    settings = get_settings()
    _require_enabled(settings)
    rows = AgentSensorRepository(session).list_policies(auth.organization_id)
    return [_policy_summary(r) for r in rows]


@router.post("/agent-scope-policies", response_model=PolicySummary, status_code=201)
def create_policy(
    body: PolicyBody, request: Request,
    auth: AuthContext = Depends(require_scope("agent_policies:manage")),
    session: Session = Depends(get_db),
) -> PolicySummary:
    settings = get_settings()
    _require_enabled(settings)
    repo = AgentSensorRepository(session)
    record = repo.create_policy(
        auth.organization_id, _policy_doc(body, str(auth.organization_id), settings)
    )
    repo.add_audit(
        organization_id=auth.organization_id, actor_id=auth.key_id, event_type="policy_created",
        request_id=_request_id(request), safe_metadata=body.name,
    )
    return _policy_summary(record)


@router.put("/agent-scope-policies/{policy_id}", response_model=PolicySummary)
def update_policy(
    policy_id: UUID, body: PolicyBody, request: Request,
    auth: AuthContext = Depends(require_scope("agent_policies:manage")),
    session: Session = Depends(get_db),
) -> PolicySummary:
    settings = get_settings()
    _require_enabled(settings)
    repo = AgentSensorRepository(session)
    try:
        record = repo.get_policy(auth.organization_id, policy_id)
    except PolicyNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "policy not found") from None
    repo.update_policy(record, _policy_doc(body, str(auth.organization_id), settings))
    repo.add_audit(
        organization_id=auth.organization_id, actor_id=auth.key_id, event_type="policy_updated",
        request_id=_request_id(request), safe_metadata=f"version={record.policy_version}",
    )
    return _policy_summary(record)


@router.delete("/agent-scope-policies/{policy_id}", status_code=204)
def delete_policy(
    policy_id: UUID, request: Request,
    auth: AuthContext = Depends(require_scope("agent_policies:manage")),
    session: Session = Depends(get_db),
) -> None:
    settings = get_settings()
    _require_enabled(settings)
    repo = AgentSensorRepository(session)
    try:
        record = repo.get_policy(auth.organization_id, policy_id)
    except PolicyNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "policy not found") from None
    repo.delete_policy(record)
    repo.add_audit(
        organization_id=auth.organization_id, actor_id=auth.key_id, event_type="policy_deleted",
        request_id=_request_id(request),
    )


# ---- sessions ------------------------------------------------------------------------------------


@router.post("/agent-sessions", response_model=SessionSummary, status_code=201)
def create_session(
    body: CreateSessionRequest, request: Request,
    auth: AuthContext = Depends(require_scope("agent_sessions:create")),
    session: Session = Depends(get_db),
) -> SessionSummary:
    settings = get_settings()
    _require_enabled(settings)
    repo = AgentSensorRepository(session)
    if repo.find_session_by_external(auth.organization_id, body.external_session_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "session already exists")
    # Resolve the caller's sensor (scoped key -> exactly one active sensor by api_key_id).
    sensor = _sensor_for_key(session, auth)
    if sensor is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "no active agent sensor for this key")
    allowed = tuple(body.allowed_paths)
    denied = tuple(body.denied_paths)
    if body.scope_policy_id is not None:
        try:
            policy = repo.get_policy(auth.organization_id, body.scope_policy_id)
        except PolicyNotFoundError:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "scope policy not found") from None
        doc = repo.policy_doc(policy)
        allowed = allowed or doc.allowed_paths
        denied = denied or doc.denied_paths
    scope = normalize_scope(
        task_summary=body.task_summary, allowed_paths=allowed, denied_paths=denied,
        max_allowed=settings.agent_scope_max_allowed_paths,
        max_denied=settings.agent_scope_max_denied_paths,
    )
    record = repo.create_session(
        organization_id=auth.organization_id, sensor_id=sensor.id,
        external_session_id=body.external_session_id, agent_type=body.agent_type,
        repository_id=body.repository_id, actor_id=auth.key_id, task_summary=scope.task_summary,
        scope_policy_id=body.scope_policy_id, scope_json=scope.to_json(),
        correlation_id=uuid4().hex,
    )
    repo.add_audit(
        organization_id=auth.organization_id, agent_sensor_id=sensor.id, session_id=record.id,
        event_type="session_started", request_id=_request_id(request),
    )
    return _session_summary(record)


@router.get("/agent-sessions", response_model=list[SessionSummary])
def list_sessions(
    auth: AuthContext = Depends(require_scope("agent_sessions:read")),
    session: Session = Depends(get_db),
) -> list[SessionSummary]:
    settings = get_settings()
    _require_enabled(settings)
    rows = AgentSensorRepository(session).list_sessions(auth.organization_id)
    return [_session_summary(r) for r in rows]


@router.get("/agent-sessions/{session_id}", response_model=SessionSummary)
def get_session(
    session_id: UUID, auth: AuthContext = Depends(require_scope("agent_sessions:read")),
    session: Session = Depends(get_db),
) -> SessionSummary:
    settings = get_settings()
    _require_enabled(settings)
    try:
        return _session_summary(
            AgentSensorRepository(session).get_session(auth.organization_id, session_id)
        )
    except SessionNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from None


@router.post("/agent-sessions/{session_id}/complete", response_model=SessionSummary)
def complete_session(
    session_id: UUID, request: Request,
    auth: AuthContext = Depends(require_scope("agent_sessions:create")),
    session: Session = Depends(get_db),
) -> SessionSummary:
    settings = get_settings()
    _require_enabled(settings)
    repo = AgentSensorRepository(session)
    try:
        record = repo.get_session(auth.organization_id, session_id)
    except SessionNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from None
    events = repo.events_for_session(session_id)
    violations = repo.violations_for_session(session_id)
    surfaces = {"database", "network", "mcp"}
    used_surfaces = {
        s for s in surfaces
        if any(e.event_type.startswith(s[:3]) or s in (e.event_type or "") for e in events)
    }
    path_classes = [PathClass(e.path_class) for e in events if e.path_class]
    summary = session_summary(
        event_count=len(events), violation_count=len(violations),
        distinct_unrelated=len({e.normalized_path for e in events if e.path_class == "unrelated"}),
        sensitive_reads=sum(1 for v in violations if "sensitive" in v.violation_type),
        surfaces=frozenset(used_surfaces),
        decoy_touched=any(e.decoy_id for e in events),
        escalation=detect_escalation(path_classes),
        modifications=any(e.event_type.startswith("file_") for e in events),
    )
    import json

    repo.complete_session(record, status="completed", summary=json.dumps(summary))
    repo.add_audit(
        organization_id=auth.organization_id, session_id=session_id, actor_id=auth.key_id,
        event_type="session_completed", request_id=_request_id(request),
    )
    return _session_summary(record)


@router.get("/agent-sessions/{session_id}/violations")
def list_violations(
    session_id: UUID, auth: AuthContext = Depends(require_scope("agent_violations:read")),
    session: Session = Depends(get_db),
) -> list[dict[str, object]]:
    settings = get_settings()
    _require_enabled(settings)
    repo = AgentSensorRepository(session)
    try:
        repo.get_session(auth.organization_id, session_id)
    except SessionNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from None
    return [
        {
            "id": str(v.id), "event_id": str(v.event_id), "violation_type": v.violation_type,
            "severity": v.severity, "confidence": v.confidence, "policy_rule": v.policy_rule,
            "explanation": v.explanation, "created_at": v.created_at.isoformat(),
        }
        for v in repo.violations_for_session(session_id)
    ]


@router.get("/agent-sessions/{session_id}/timeline")
def session_timeline(
    session_id: UUID, auth: AuthContext = Depends(require_scope("agent_sessions:read")),
    session: Session = Depends(get_db),
) -> list[dict[str, object]]:
    settings = get_settings()
    _require_enabled(settings)
    repo = AgentSensorRepository(session)
    try:
        repo.get_session(auth.organization_id, session_id)
    except SessionNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from None
    return [
        {
            "id": str(e.id), "event_type": e.event_type, "normalized_path": e.normalized_path,
            "path_class": e.path_class, "tool_name": e.tool_name, "resource_type": e.resource_type,
            "decoy_id": e.decoy_id, "trace_id": e.trace_id, "result_status": e.result_status,
            "minimized_metadata": e.minimized_metadata, "observed_at": e.observed_at.isoformat(),
        }
        for e in repo.events_for_session(session_id)
    ]


# ---- signed event ingestion ----------------------------------------------------------------------


def _sensor_for_key(session: Session, auth: AuthContext):  # type: ignore[no-untyped-def]
    from sqlalchemy import select as _select

    from app.models.records import AgentSensorRecord

    return session.scalars(
        _select(AgentSensorRecord).where(
            AgentSensorRecord.organization_id == auth.organization_id,
            AgentSensorRecord.api_key_id == auth.key_id,
            AgentSensorRecord.status == "active",
        )
    ).first()


def _rebuild_aggregate(events, policy, decoy_index) -> SessionAggregate:  # type: ignore[no-untyped-def]
    """Replay prior stored events through the deterministic engine to rebuild the running
    aggregate. Bounded by the event query limit."""
    agg = SessionAggregate()
    for e in events:
        try:
            etype = AgentEventType(e.event_type)
        except ValueError:
            continue
        evaluate(
            event_type=etype, normalized_path=e.normalized_path, tool_name=e.tool_name,
            resource_type=e.resource_type, decoy_id=e.decoy_id, policy=policy,
            decoy_paths=decoy_index.path_set(), agg=agg,
        )
    return agg


@router.post("/monitoring/agent-events", response_model=AgentEventResponse, tags=["monitoring"])
def ingest_agent_event(
    body: AgentEventRequest,
    request: Request,
    raw_body: bytes = Depends(_raw_body),
    auth: AuthContext = Depends(require_scope("agent_events:ingest")),
    session: Session = Depends(get_db),
    x_deceptiforge_nonce: str | None = Header(default=None),
    x_deceptiforge_timestamp: str | None = Header(default=None),
    x_deceptiforge_sensor_id: str | None = Header(default=None),
    x_deceptiforge_signature: str | None = Header(default=None),
) -> AgentEventResponse:
    settings = get_settings()
    _require_enabled(settings)
    request_id = _request_id(request)
    org = str(auth.organization_id)
    svc = AgentSensorService(session, settings)
    repo = AgentSensorRepository(session)
    if len(raw_body) > settings.agent_sensor_event_max_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "agent event too large")
    try:
        event_type = AgentEventType(body.event_type)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown event type") from None

    require_sig = settings.require_signed_agent_events and settings.auth_enabled
    if require_sig and settings.monitor_signature_required:
        try:
            verified = svc.verify_request(
                organization_id=auth.organization_id, sensor_public_id=x_deceptiforge_sensor_id,
                timestamp=x_deceptiforge_timestamp, nonce=x_deceptiforge_nonce,
                signature=x_deceptiforge_signature, method=request.method,
                path=request.url.path, body=raw_body,
            )
            sensor_id = verified.sensor_id
        except SensorSignatureError as error:
            repo.add_audit(
                organization_id=auth.organization_id, event_type="signature_failure",
                request_id=request_id,
            )
            emit("agent_event_signature_failed", request_id=request_id, organization_id=org)
            raise HTTPException(error.status_code, error.message) from None
    else:
        sensor = _sensor_for_key(session, auth)
        if sensor is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sensor not active")
        sensor_id = sensor.id
        svc.touch(sensor, version=None)
    if settings.auth_enabled:
        try:
            get_replay_guard().check(x_deceptiforge_nonce, x_deceptiforge_timestamp, scope=org)
        except ReplayError as error:
            emit("agent_event_replay_rejected", request_id=request_id, organization_id=org)
            raise HTTPException(error.status_code, error.message) from None

    session_record = repo.find_session_by_external(auth.organization_id, body.session_external_id)
    if session_record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown session")
    if session_record.sensor_id != sensor_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "session belongs to another sensor")
    if session_record.status != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "session is not active")

    policy = _scope_policy(repo, session_record, settings, org)
    decoy_index = repo.build_decoy_index(auth.organization_id)
    normalized = normalize_path(body.path) if body.path else None
    decoy_id = resolve_decoy(
        trace_id=body.trace_id, normalized_path=normalized,
        resource_id_hash=body.resource_id_hash, index=decoy_index,
    )
    prior = repo.events_for_session(session_record.id)
    agg = _rebuild_aggregate(prior, policy, decoy_index)
    decision = evaluate(
        event_type=event_type, normalized_path=normalized, tool_name=body.tool_name,
        resource_type=body.resource_type, decoy_id=decoy_id, policy=policy,
        decoy_paths=decoy_index.path_set(), agg=agg,
    )
    minimized = MinimizedAgentEvent(
        external_event_id=body.external_event_id, session_id=str(session_record.id),
        event_type=event_type, normalized_path=normalized, tool_name=body.tool_name,
        resource_type=body.resource_type, resource_id_hash=body.resource_id_hash,
        trace_id=body.trace_id, result_status=body.result_status,
        minimized_metadata=minimize_metadata(body.metadata),
        observed_at=body.observed_at or datetime.now(UTC),
    )
    record, created = repo.add_event(
        organization_id=auth.organization_id, sensor_id=sensor_id, session_id=session_record.id,
        event=minimized, decision=decision, repository_id=session_record.repository_id,
        correlation_id=session_record.correlation_id,
    )
    if not created:
        return AgentEventResponse(
            accepted=True, idempotent=True, path_class=decision.path_class.value,
            violation_type=None, severity="info", explanation="duplicate event ignored",
        )
    assert record is not None
    if decision.violation_type is not None:
        repo.add_violation(
            organization_id=auth.organization_id, session_id=session_record.id,
            event_id=record.id, decision=decision,
        )
        exposure = exposure_for(decision.violation_type)
        sev = incident_severity(
            exposure, violation_count=agg.violation_count,
            cross_surface=len(agg.surfaces) >= 1 and bool(decoy_id),
            modifications=agg.modifications,
        )
        repo.add_audit(
            organization_id=auth.organization_id, agent_sensor_id=sensor_id,
            session_id=session_record.id, event_type="violation_generated",
            request_id=request_id, safe_metadata=decision.violation_type.value,
        )
        emit(
            "agent_event_violation", request_id=request_id, organization_id=org,
            violation=decision.violation_type.value, exposure=exposure.value, severity=sev.value,
        )
    return AgentEventResponse(
        accepted=True, idempotent=False, path_class=decision.path_class.value,
        violation_type=decision.violation_type.value if decision.violation_type else None,
        severity=decision.severity.value, explanation=decision.explanation,
    )


def _scope_policy(repo, session_record, settings, org) -> AgentScopePolicyDoc:  # type: ignore[no-untyped-def]
    import json

    scope = json.loads(session_record.scope_data or "{}")
    return AgentScopePolicyDoc(
        organization_id=org, name="session-scope",
        allowed_paths=tuple(scope.get("allowed_paths", [])),
        denied_paths=tuple(scope.get("denied_paths", [])),
        allowed_tools=tuple(scope.get("allowed_tools", [])),
        denied_tools=tuple(scope.get("denied_tools", [])),
        allowed_resource_types=tuple(scope.get("allowed_resource_types", [])),
    )
