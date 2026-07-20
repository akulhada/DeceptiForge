# Purpose: HTTP surface for SIEM/SOAR integrations, delivery history, and manual incident export.
# Responsibilities: create/list/get/test/disable integrations (SSRF-validated endpoints, encrypted
#   secrets never returned), read + manually retry deliveries + dead letters, and export incidents/
#   alerts/coverage in standard formats. Test connection sends only a synthetic labeled event and is
#   rate-limited + audited. Org + permission scoped. Dependencies: repository, adapters, http, ssrf,
#   export, settings, auth.
from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.dependencies import get_db
from app.models.domain.integrations import (
    EventType,
    IntegrationType,
    PayloadProfile,
    SecurityEventEnvelope,
)
from app.models.domain.operations import Severity
from app.models.records import AlertRecord, IncidentRecord
from app.repositories.integrations import IntegrationNotFoundError, IntegrationRepository
from app.security import require_scope
from app.services.api_keys import AuthContext
from app.services.integrations import export, mapping
from app.services.integrations.adapter import AdapterConfig, TransportError
from app.services.integrations.adapters import get_adapter
from app.services.integrations.http import build_http_transport
from app.services.integrations.ssrf import SsrfError, validate_endpoint
from app.services.metrics import emit
from app.services.rate_limit import get_rate_limiter, rate_limit_key

router = APIRouter(tags=["integrations"])


# ---- schemas -------------------------------------------------------------------------------------


class CreateIntegrationRequest(BaseModel):
    integration_type: IntegrationType
    name: str = Field(min_length=1, max_length=128)
    endpoint: str = Field(min_length=1, max_length=1024)
    secret: str | None = Field(default=None, max_length=4096)
    options: dict[str, str] = Field(default_factory=dict)
    event_types: list[str] = Field(default_factory=list, max_length=32)
    surface_types: list[str] = Field(default_factory=list, max_length=10)
    minimum_severity: Severity = Severity.INFO
    payload_profile: PayloadProfile = PayloadProfile.MINIMAL
    include_narrative: bool = False
    include_coverage_events: bool = True
    include_operational_events: bool = True


class IntegrationSummary(BaseModel):
    id: UUID
    integration_type: str
    name: str
    status: str
    endpoint_reference: str
    payload_profile: str
    minimum_severity: str
    include_narrative: bool
    last_tested_at: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    safe_failure_code: str | None
    created_at: datetime


def _summary(r) -> IntegrationSummary:  # type: ignore[no-untyped-def]
    return IntegrationSummary(
        id=r.id, integration_type=r.integration_type, name=r.name, status=r.status,
        endpoint_reference=r.endpoint_reference, payload_profile=r.payload_profile,
        minimum_severity=r.minimum_severity, include_narrative=r.include_narrative,
        last_tested_at=r.last_tested_at, last_success_at=r.last_success_at,
        last_failure_at=r.last_failure_at, safe_failure_code=r.safe_failure_code,
        created_at=r.created_at,
    )


def _require_enabled(settings: Settings) -> None:
    if not settings.security_integrations_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "security integrations are not enabled")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _repo(session: Session, settings: Settings) -> IntegrationRepository:
    return IntegrationRepository(session, settings)


# ---- integrations --------------------------------------------------------------------------------


@router.post("/security-integrations", response_model=IntegrationSummary, status_code=201)
def create_integration(
    body: CreateIntegrationRequest, request: Request,
    auth: AuthContext = Depends(require_scope("integrations:manage")),
    session: Session = Depends(get_db),
) -> IntegrationSummary:
    settings = get_settings()
    _require_enabled(settings)
    try:
        validate_endpoint(body.endpoint, settings)  # SSRF check before persisting
    except SsrfError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from None
    repo = _repo(session, settings)
    routing_json = json.dumps(
        {"event_types": body.event_types, "surface_types": body.surface_types}
    )
    record = repo.create_integration(
        organization_id=auth.organization_id, integration_type=body.integration_type.value,
        name=body.name, endpoint=body.endpoint, secret=body.secret,
        config_json=json.dumps(body.options), routing_json=routing_json,
        payload_profile=body.payload_profile.value, minimum_severity=body.minimum_severity.value,
        include_narrative=body.include_narrative, include_coverage=body.include_coverage_events,
        include_operational=body.include_operational_events, created_by_actor_id=auth.key_id,
    )
    repo.add_audit(
        organization_id=auth.organization_id, integration_id=record.id, actor_id=auth.key_id,
        event_type="integration_created", request_id=_request_id(request),
        safe_metadata=body.integration_type.value,
    )
    return _summary(record)


@router.get("/security-integrations", response_model=list[IntegrationSummary])
def list_integrations(
    auth: AuthContext = Depends(require_scope("integrations:read")),
    session: Session = Depends(get_db),
) -> list[IntegrationSummary]:
    settings = get_settings()
    _require_enabled(settings)
    return [_summary(r) for r in _repo(session, settings).list_integrations(auth.organization_id)]


@router.post("/security-integrations/{integration_id}/disable", response_model=IntegrationSummary)
def disable_integration(
    integration_id: UUID, request: Request,
    auth: AuthContext = Depends(require_scope("integrations:manage")),
    session: Session = Depends(get_db),
) -> IntegrationSummary:
    settings = get_settings()
    _require_enabled(settings)
    repo = _repo(session, settings)
    try:
        record = repo.get_integration(auth.organization_id, integration_id)
    except IntegrationNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "integration not found") from None
    repo.set_status(record, "revoked")
    repo.add_audit(
        organization_id=auth.organization_id, integration_id=integration_id, actor_id=auth.key_id,
        event_type="integration_disabled", request_id=_request_id(request),
    )
    return _summary(record)


@router.post("/security-integrations/{integration_id}/test")
def test_integration(
    integration_id: UUID, request: Request,
    auth: AuthContext = Depends(require_scope("integrations:test")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    _require_enabled(settings)
    repo = _repo(session, settings)
    try:
        record = repo.get_integration(auth.organization_id, integration_id)
    except IntegrationNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "integration not found") from None
    if not get_rate_limiter().allow(
        rate_limit_key(
            endpoint="integrations:test", organization_id=auth.organization_id,
            actor=auth.key_id, resource=str(integration_id),
        ),
        6,
    ):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "test rate limit exceeded")
    try:
        validate_endpoint(record.endpoint_reference, settings)
    except SsrfError as error:
        repo.add_audit(
            organization_id=auth.organization_id, integration_id=integration_id,
            event_type="ssrf_rejected", request_id=_request_id(request),
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from None
    # Synthetic, clearly-labeled test event — never a real incident.
    envelope = mapping.build_operational_event(
        event_type=EventType.CONNECTOR_UNHEALTHY, org=str(auth.organization_id),
        occurred_at=datetime.now(UTC), object_id=f"test-{uuid4().hex[:8]}", severity=Severity.INFO,
        title="DeceptiForge integration test", summary="synthetic test event; ignore",
    )
    adapter = get_adapter(record.integration_type)
    config = AdapterConfig(
        endpoint=record.endpoint_reference, secret=repo.resolve_secret(record),
        options=json.loads(record.config_data or "{}"),
    )
    http_request = adapter.build_request(envelope, config, delivery_id="test")
    try:
        response = build_http_transport().send(
            http_request, timeout=settings.security_export_timeout_seconds
        )
        result = adapter.classify_response(response)
        ok = result.response_status is not None and 200 <= result.response_status < 300
    except TransportError:
        ok = False
    repo.set_status(record, "active" if ok else "degraded", tested=True, success=ok, failure=not ok)
    repo.add_audit(
        organization_id=auth.organization_id, integration_id=integration_id, actor_id=auth.key_id,
        event_type="integration_tested", request_id=_request_id(request),
        safe_metadata=f"ok={ok}",
    )
    return {"ok": ok, "status": record.status}


# ---- deliveries ----------------------------------------------------------------------------------


@router.get("/integration-deliveries")
def list_deliveries(
    auth: AuthContext = Depends(require_scope("integrations:deliveries:read")),
    session: Session = Depends(get_db),
) -> list[dict[str, object]]:
    settings = get_settings()
    _require_enabled(settings)
    return [
        {
            "id": str(d.id), "integration_id": str(d.integration_id), "source_type": d.source_type,
            "source_id": d.source_id, "event_type": d.event_type, "status": d.status,
            "attempt_count": d.attempt_count, "response_status": d.response_status,
            "safe_error_code": d.safe_error_code, "created_at": d.created_at.isoformat(),
            "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
        }
        for d in _repo(session, settings).list_deliveries(auth.organization_id)
    ]


@router.get("/integration-dead-letters")
def list_dead_letters(
    auth: AuthContext = Depends(require_scope("integrations:deliveries:read")),
    session: Session = Depends(get_db),
) -> list[dict[str, object]]:
    settings = get_settings()
    _require_enabled(settings)
    return [
        {
            "id": str(d.id), "integration_id": str(d.integration_id),
            "delivery_id": str(d.delivery_id), "reason_code": d.reason_code,
            "attempt_count": d.attempt_count, "payload_hash": d.payload_hash,
            "final_failed_at": d.final_failed_at.isoformat(),
        }
        for d in _repo(session, settings).dead_letters(auth.organization_id)
    ]


@router.post("/integration-deliveries/{delivery_id}/retry")
def retry_delivery(
    delivery_id: UUID, request: Request,
    auth: AuthContext = Depends(require_scope("integrations:deliveries:retry")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    _require_enabled(settings)
    repo = _repo(session, settings)
    record = repo.get_delivery(auth.organization_id, delivery_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "delivery not found")
    repo.requeue_delivery(record)
    repo.add_audit(
        organization_id=auth.organization_id, delivery_id=delivery_id, actor_id=auth.key_id,
        event_type="manual_retry", request_id=_request_id(request),
    )
    return {"status": "queued"}


# ---- manual export -------------------------------------------------------------------------------

_FORMATS = ("json", "jsonl", "csv", "markdown", "stix")


def _incident_envelope(record: IncidentRecord) -> SecurityEventEnvelope:
    data = json.loads(record.data or "{}")
    return mapping.build_incident_event(
        event_type=EventType.INCIDENT_CREATED, org=str(record.organization_id),
        occurred_at=record.created_at, incident_id=str(record.id),
        severity=Severity(str(data.get("severity", "medium"))),
        title=str(data.get("title", "Incident"))[:256],
        summary=str(data.get("summary", ""))[:1024], confidence=float(data.get("confidence", 1.0)),
        incident_status=str(record.status or "open"),
        affected_surfaces=tuple(data.get("affected_surfaces", []))[:20],
        recommended_actions=tuple(data.get("recommended_actions", []))[:10],
        evidence_summary=str(data.get("evidence_summary", ""))[:1024],
    )


@router.get("/security-export/incidents/{incident_id}")
def export_incident(
    incident_id: UUID, request: Request, format: str = "json",
    auth: AuthContext = Depends(require_scope("incidents:export")),
    session: Session = Depends(get_db),
) -> Response:
    settings = get_settings()
    _require_enabled(settings)
    if format not in _FORMATS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unsupported format")
    record = session.get(IncidentRecord, incident_id)
    if record is None or record.organization_id != auth.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "incident not found")
    content_type, body = export.render([_incident_envelope(record)], format)
    _repo(session, settings).add_audit(
        organization_id=auth.organization_id, actor_id=auth.key_id, event_type="manual_export",
        request_id=_request_id(request), safe_metadata=f"incident:{format}",
    )
    emit("integration_manual_export", organization_id=str(auth.organization_id), fmt=format)
    return Response(content=body, media_type=content_type)


@router.get("/security-export/alerts/{alert_id}")
def export_alert(
    alert_id: UUID, request: Request, format: str = "json",
    auth: AuthContext = Depends(require_scope("alerts:export")),
    session: Session = Depends(get_db),
) -> Response:
    settings = get_settings()
    _require_enabled(settings)
    if format not in _FORMATS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unsupported format")
    record = session.get(AlertRecord, alert_id)
    if record is None or record.organization_id != auth.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "alert not found")
    data = json.loads(record.data or "{}")
    envelope = mapping.build_alert_event(
        event_type=EventType.ALERT_CREATED, org=str(auth.organization_id),
        occurred_at=record.created_at, alert_id=str(record.id),
        severity=Severity(str(data.get("severity", "medium"))),
        title=str(data.get("title", "Alert"))[:256], summary=str(data.get("summary", ""))[:1024],
        confidence=float(data.get("confidence", 1.0)),
        trace_ids=(record.trace_identifier,),
    )
    content_type, body = export.render([envelope], format)
    _repo(session, settings).add_audit(
        organization_id=auth.organization_id, actor_id=auth.key_id, event_type="manual_export",
        request_id=_request_id(request), safe_metadata=f"alert:{format}",
    )
    return Response(content=body, media_type=content_type)
