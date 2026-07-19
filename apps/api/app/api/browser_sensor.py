# Purpose: HTTP surface for browser AI-paste sensors — enrollment, sensor lifecycle, organization
#   policy, the scoped trace registry, and trusted signed minimized event ingestion.
# Responsibilities: enrollment token creation (admin) + one-time enroll (token-authenticated only),
#   sensor list/get/revoke/rotate, policy read/update (monotonic version), registry fetch (hashed
#   tokens only), and signed + replay-protected + minimized event ingestion with deterministic
#   classification. Secrets shown once; never returned again or logged. Org + permission scoped.
# Dependencies: services, repository, monitor signing/replay, settings, auth.
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.dependencies import get_db
from app.models.domain.browser_sensor import (
    BrowserAiPolicyDoc,
    BrowserEventType,
    DestinationClass,
    DomainRule,
    MatchMethod,
    MinimizedBrowserEvent,
    TraceMatchMode,
    TraceRegistryDoc,
)
from app.repositories.browser_sensor import BrowserSensorRepository
from app.security import require_scope
from app.services.api_keys import AuthContext
from app.services.browser_sensor.classification import classify, severity
from app.services.browser_sensor.minimize import minimize_metadata
from app.services.browser_sensor.policy import build_policy_doc, classify_destination
from app.services.browser_sensor.registry import build_registry
from app.services.browser_sensor.service import (
    BrowserSensorService,
    EnrollmentError,
    SensorSignatureError,
)
from app.services.metrics import emit
from app.services.replay import ReplayError, get_replay_guard

router = APIRouter(tags=["browser-sensors"])


# ---- schemas -------------------------------------------------------------------------------------


class EnrollmentTokenResponse(BaseModel):
    token: str  # shown once
    expires_at: datetime


class EnrollRequest(BaseModel):
    token: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    installation_id: str = Field(min_length=1, max_length=128)
    browser_family: str = Field(min_length=1, max_length=32)
    extension_version: str = Field(min_length=1, max_length=32)
    device_label: str | None = Field(default=None, max_length=128)


class EnrollResponse(BaseModel):
    sensor_id: UUID
    sensor_public_id: str
    signing_secret: str  # shown once
    api_key: str  # shown once


class SensorSummary(BaseModel):
    id: UUID
    sensor_public_id: str
    name: str
    device_label: str | None
    browser_family: str
    extension_version: str
    status: str
    last_seen_at: datetime | None
    created_at: datetime


class RotateResponse(BaseModel):
    signing_secret: str  # shown once


class DomainRuleModel(BaseModel):
    domain: str = Field(min_length=1, max_length=253)
    classification: DestinationClass
    label: str | None = Field(default=None, max_length=64)


class PolicyUpdateRequest(BaseModel):
    enabled: bool = False
    trace_match_mode: TraceMatchMode = TraceMatchMode.EXACT
    local_only_mode: bool = False
    event_reporting_enabled: bool = True
    show_user_notification: bool = True
    allow_pause: bool = True
    min_extension_version: str = Field(default="0.1.0", max_length=32)
    rules: list[DomainRuleModel] = Field(default_factory=list, max_length=500)


class BrowserEventRequest(BaseModel):
    trace_id: str = Field(min_length=1, max_length=128)
    destination_domain: str = Field(min_length=1, max_length=253)
    event_type: str
    match_method: str
    confidence: float = Field(ge=0, le=1, default=1.0)
    extension_version: str = Field(max_length=32, default="0.0.0")
    policy_version: int = 0
    excerpt_hash: str | None = Field(default=None, max_length=128)
    metadata: dict[str, str] = Field(default_factory=dict)
    observed_at: datetime | None = None


class BrowserEventResponse(BaseModel):
    accepted: bool
    destination_classification: str
    exposure_type: str
    severity: str
    event_count: int


class BrowserEventSummary(BaseModel):
    id: UUID
    browser_sensor_id: UUID
    trace_id: str
    destination_domain: str
    destination_classification: str
    event_type: str
    match_method: str
    confidence: float
    extension_version: str
    policy_version: int
    minimized_metadata: str
    correlation_id: str
    observed_at: datetime


def _sensor_summary(r) -> SensorSummary:  # type: ignore[no-untyped-def]
    return SensorSummary(
        id=r.id, sensor_public_id=r.sensor_public_id, name=r.name, device_label=r.device_label,
        browser_family=r.browser_family, extension_version=r.extension_version, status=r.status,
        last_seen_at=r.last_seen_at, created_at=r.created_at,
    )


# ---- helpers -------------------------------------------------------------------------------------


def _require_enabled(settings: Settings) -> None:
    if not settings.browser_sensor_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "browser sensors are not enabled")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


async def _raw_body(request: Request) -> bytes:
    return await request.body()


# ---- enrollment ----------------------------------------------------------------------------------


@router.post(
    "/browser-sensors/enrollment-tokens",
    response_model=EnrollmentTokenResponse,
    status_code=201,
)
def create_enrollment_token(
    request: Request,
    auth: AuthContext = Depends(require_scope("browser_sensors:manage")),
    session: Session = Depends(get_db),
) -> EnrollmentTokenResponse:
    settings = get_settings()
    _require_enabled(settings)
    svc = BrowserSensorService(session, settings)
    record, token = svc.create_enrollment_token(
        auth.organization_id, created_by_actor_id=auth.key_id
    )
    BrowserSensorRepository(session).add_audit(
        organization_id=auth.organization_id, actor_id=auth.key_id,
        event_type="enrollment_token_created", request_id=_request_id(request),
    )
    return EnrollmentTokenResponse(token=token, expires_at=record.expires_at)


@router.post("/browser-sensors/enroll", response_model=EnrollResponse, status_code=201)
def enroll(
    body: EnrollRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> EnrollResponse:
    # Token-authenticated only: the extension has no dashboard key yet. The token binds the org.
    settings = get_settings()
    _require_enabled(settings)
    svc = BrowserSensorService(session, settings)
    try:
        result = svc.enroll(
            token=body.token, name=body.name, installation_id=body.installation_id,
            browser_family=body.browser_family, extension_version=body.extension_version,
            device_label=body.device_label,
        )
    except EnrollmentError as error:
        raise HTTPException(error.status_code, error.message) from None
    BrowserSensorRepository(session).add_audit(
        organization_id=result.sensor.organization_id, browser_sensor_id=result.sensor.id,
        event_type="sensor_enrolled", request_id=_request_id(request),
        safe_metadata=result.sensor_public_id,
    )
    return EnrollResponse(
        sensor_id=result.sensor.id, sensor_public_id=result.sensor_public_id,
        signing_secret=result.signing_secret, api_key=result.api_key,
    )


# ---- sensor lifecycle ----------------------------------------------------------------------------


@router.get("/browser-sensors", response_model=list[SensorSummary])
def list_sensors(
    auth: AuthContext = Depends(require_scope("browser_sensors:read")),
    session: Session = Depends(get_db),
) -> list[SensorSummary]:
    settings = get_settings()
    _require_enabled(settings)
    rows = BrowserSensorService(session, settings).list(auth.organization_id)
    return [_sensor_summary(r) for r in rows]


@router.get("/browser-sensors/{sensor_id}", response_model=SensorSummary)
def get_sensor(
    sensor_id: UUID,
    auth: AuthContext = Depends(require_scope("browser_sensors:read")),
    session: Session = Depends(get_db),
) -> SensorSummary:
    settings = get_settings()
    _require_enabled(settings)
    record = BrowserSensorService(session, settings).get(auth.organization_id, sensor_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sensor not found")
    return _sensor_summary(record)


@router.post("/browser-sensors/{sensor_id}/revoke", response_model=SensorSummary)
def revoke_sensor(
    sensor_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_scope("browser_sensors:manage")),
    session: Session = Depends(get_db),
) -> SensorSummary:
    settings = get_settings()
    _require_enabled(settings)
    svc = BrowserSensorService(session, settings)
    record = svc.get(auth.organization_id, sensor_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sensor not found")
    svc.revoke(record)
    BrowserSensorRepository(session).add_audit(
        organization_id=auth.organization_id, browser_sensor_id=sensor_id, actor_id=auth.key_id,
        event_type="sensor_revoked", request_id=_request_id(request),
    )
    return _sensor_summary(record)


@router.post("/browser-sensors/{sensor_id}/rotate", response_model=RotateResponse)
def rotate_sensor(
    sensor_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_scope("browser_sensors:manage")),
    session: Session = Depends(get_db),
) -> RotateResponse:
    settings = get_settings()
    _require_enabled(settings)
    svc = BrowserSensorService(session, settings)
    record = svc.get(auth.organization_id, sensor_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sensor not found")
    try:
        secret = svc.rotate_secret(record)
    except EnrollmentError as error:
        raise HTTPException(error.status_code, error.message) from None
    BrowserSensorRepository(session).add_audit(
        organization_id=auth.organization_id, browser_sensor_id=sensor_id, actor_id=auth.key_id,
        event_type="credential_rotated", request_id=_request_id(request),
    )
    return RotateResponse(signing_secret=secret)


# ---- policy --------------------------------------------------------------------------------------


@router.get("/browser-ai-policy", response_model=BrowserAiPolicyDoc)
def get_policy(
    auth: AuthContext = Depends(require_scope("browser_policy:read")),
    session: Session = Depends(get_db),
) -> BrowserAiPolicyDoc:
    settings = get_settings()
    _require_enabled(settings)
    repo = BrowserSensorRepository(session)
    record = repo.get_policy(auth.organization_id)
    if record is None:
        record = repo.upsert_policy(
            auth.organization_id, enabled=False, trace_match_mode="exact", local_only_mode=False,
            event_reporting_enabled=True, show_user_notification=True, allow_pause=True,
            min_extension_version=settings.browser_sensor_min_extension_version, rules=(),
        )
    return build_policy_doc(record, settings)


@router.put("/browser-ai-policy", response_model=BrowserAiPolicyDoc)
def update_policy(
    body: PolicyUpdateRequest,
    request: Request,
    auth: AuthContext = Depends(require_scope("browser_policy:manage")),
    session: Session = Depends(get_db),
) -> BrowserAiPolicyDoc:
    settings = get_settings()
    _require_enabled(settings)
    repo = BrowserSensorRepository(session)
    rules = tuple(
        DomainRule(domain=r.domain, classification=r.classification, label=r.label)
        for r in body.rules
    )
    record = repo.upsert_policy(
        auth.organization_id, enabled=body.enabled,
        trace_match_mode=body.trace_match_mode.value, local_only_mode=body.local_only_mode,
        event_reporting_enabled=body.event_reporting_enabled,
        show_user_notification=body.show_user_notification, allow_pause=body.allow_pause,
        min_extension_version=body.min_extension_version, rules=rules,
    )
    repo.add_audit(
        organization_id=auth.organization_id, actor_id=auth.key_id, event_type="policy_changed",
        request_id=_request_id(request), safe_metadata=f"version={record.policy_version}",
    )
    return build_policy_doc(record, settings)


@router.get("/browser-trace-registry", response_model=TraceRegistryDoc)
def get_trace_registry(
    request: Request,
    auth: AuthContext = Depends(require_scope("browser_policy:read")),
    session: Session = Depends(get_db),
) -> TraceRegistryDoc:
    settings = get_settings()
    _require_enabled(settings)
    doc = build_registry(session, auth.organization_id, settings)
    BrowserSensorRepository(session).add_audit(
        organization_id=auth.organization_id, actor_id=auth.key_id,
        event_type="registry_synchronized", request_id=_request_id(request),
        safe_metadata=f"entries={len(doc.entries)}",
    )
    return doc


# ---- events -------------------------------------------------------------------


@router.get("/browser-events", response_model=list[BrowserEventSummary])
def list_events(
    auth: AuthContext = Depends(require_scope("browser_events:read")),
    session: Session = Depends(get_db),
) -> list[BrowserEventSummary]:
    settings = get_settings()
    _require_enabled(settings)
    rows = BrowserSensorRepository(session).events_for_org(auth.organization_id)
    return [
        BrowserEventSummary(
            id=r.id, browser_sensor_id=r.browser_sensor_id, trace_id=r.trace_id,
            destination_domain=r.destination_domain,
            destination_classification=r.destination_classification, event_type=r.event_type,
            match_method=r.match_method, confidence=r.confidence,
            extension_version=r.extension_version, policy_version=r.policy_version,
            minimized_metadata=r.minimized_metadata, correlation_id=r.correlation_id,
            observed_at=r.observed_at,
        )
        for r in rows
    ]


@router.post(
    "/monitoring/browser-events", response_model=BrowserEventResponse, tags=["monitoring"]
)
def ingest_browser_event(
    body: BrowserEventRequest,
    request: Request,
    raw_body: bytes = Depends(_raw_body),
    auth: AuthContext = Depends(require_scope("browser_events:ingest")),
    session: Session = Depends(get_db),
    x_deceptiforge_nonce: str | None = Header(default=None),
    x_deceptiforge_timestamp: str | None = Header(default=None),
    x_deceptiforge_sensor_id: str | None = Header(default=None),
    x_deceptiforge_signature: str | None = Header(default=None),
) -> BrowserEventResponse:
    settings = get_settings()
    _require_enabled(settings)
    request_id = _request_id(request)
    org = str(auth.organization_id)
    svc = BrowserSensorService(session, settings)
    repo = BrowserSensorRepository(session)
    try:
        event_type = BrowserEventType(body.event_type)
        match_method = MatchMethod(body.match_method)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown event/match type") from None
    # Tamper-evidence: verify the sensor signature (identifies the specific installation).
    if settings.auth_enabled and settings.monitor_signature_required:
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
            emit("browser_event_signature_failed", request_id=request_id, organization_id=org)
            raise HTTPException(error.status_code, error.message) from None
    else:
        # Development bypass: resolve the sensor by public id without signature enforcement.
        record = None
        if x_deceptiforge_sensor_id:
            from sqlalchemy import select as _select

            from app.models.records import BrowserSensorRecord

            record = session.scalars(
                _select(BrowserSensorRecord).where(
                    BrowserSensorRecord.sensor_public_id == x_deceptiforge_sensor_id,
                    BrowserSensorRecord.organization_id == auth.organization_id,
                )
            ).first()
        if record is None or record.status != "active":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sensor not active")
        sensor_id = record.id
        svc.touch(record, extension_version=body.extension_version)
    if settings.auth_enabled:
        try:
            get_replay_guard().check(x_deceptiforge_nonce, x_deceptiforge_timestamp, scope=org)
        except ReplayError as error:
            emit("browser_event_replay_rejected", request_id=request_id, organization_id=org)
            raise HTTPException(error.status_code, error.message) from None
    # Server-side destination classification — the extension's guess is not trusted.
    policy = repo.get_policy(auth.organization_id)
    rules = build_policy_doc(policy, settings).rules if policy is not None else ()
    destination, _label = classify_destination(body.destination_domain, rules)
    observed = body.observed_at or datetime.now(UTC)
    event = MinimizedBrowserEvent(
        browser_sensor_id=str(sensor_id), trace_id=body.trace_id,
        destination_domain=body.destination_domain, destination_classification=destination,
        event_type=event_type, match_method=match_method, confidence=body.confidence,
        extension_version=body.extension_version, policy_version=body.policy_version,
        excerpt_hash=body.excerpt_hash, minimized_metadata=minimize_metadata(body.metadata),
        observed_at=observed,
    )
    correlation_id = uuid4().hex
    repo.add_event(auth.organization_id, event, correlation_id=correlation_id)
    repo.add_audit(
        organization_id=auth.organization_id, browser_sensor_id=sensor_id,
        event_type="browser_event_accepted", request_id=request_id,
        safe_metadata=f"{event_type.value}:{destination.value}",
    )
    # Deterministic exposure + severity over this trace's events across sensors/tools.
    trace_events = repo.events_for_trace(auth.organization_id, body.trace_id)
    distinct_tools = len({e.destination_domain for e in trace_events})
    exposure = classify(event_type, destination, distinct_tools=distinct_tools)
    sev = severity(
        exposure, event_count=len(trace_events), distinct_tools=distinct_tools,
        cross_surface=_seen_on_other_surfaces(session, auth.organization_id, body.trace_id),
    )
    emit(
        "browser_event_accepted", request_id=request_id, organization_id=org,
        classification=destination.value, exposure=exposure.value, severity=sev.value,
    )
    return BrowserEventResponse(
        accepted=True, destination_classification=destination.value, exposure_type=exposure.value,
        severity=sev.value, event_count=len(trace_events),
    )


def _seen_on_other_surfaces(session: Session, organization_id: UUID, trace_id: str) -> bool:
    """True when the same trace is also a decoy on a non-browser surface (RAG/MCP/repo/db)."""
    from sqlalchemy import select as _select

    from app.models.records import (
        AiTripwireDeploymentRecord,
        DatabaseHoneyRecordRecord,
        DeploymentTripwireRecord,
    )

    ai = session.scalars(
        _select(AiTripwireDeploymentRecord.id).where(
            AiTripwireDeploymentRecord.organization_id == organization_id,
            AiTripwireDeploymentRecord.trace_id == trace_id,
        )
    ).first()
    repo_tw = session.scalars(
        _select(DeploymentTripwireRecord.id).where(
            DeploymentTripwireRecord.organization_id == organization_id,
            DeploymentTripwireRecord.trace_identifier == trace_id,
        )
    ).first()
    honey = session.scalars(
        _select(DatabaseHoneyRecordRecord.id).where(
            DatabaseHoneyRecordRecord.organization_id == organization_id,
            DatabaseHoneyRecordRecord.trace_id == trace_id,
        )
    ).first()
    return any((ai, repo_tw, honey))
