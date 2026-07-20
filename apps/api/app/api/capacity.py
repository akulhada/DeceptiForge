"""Authorized tenant usage and platform capacity read/write endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.dependencies import get_db
from app.models.records import PerformanceRunRecord
from app.security import require_scope
from app.services.api_keys import AuthContext, write_audit
from app.services.capacity import TenantCapacityService, TenantLimits

router = APIRouter(tags=["capacity"])


class TenantLimitResponse(BaseModel):
    tier: str
    monitoring_events_per_second: int
    monitoring_burst: int
    max_pending_jobs: int
    max_concurrent_scans: int
    max_concurrent_deployments: int
    max_report_jobs: int


class TenantLimitRequest(TenantLimitResponse):
    pass


class PerformanceRunResponse(BaseModel):
    id: UUID
    methodology_version: str
    code_revision: str
    infrastructure: dict[str, object]
    workload: dict[str, object]
    results: dict[str, object]
    status: str


def _service(session: Session) -> TenantCapacityService:
    return TenantCapacityService(session, get_settings())


def _limits(value: TenantLimits) -> TenantLimitResponse:
    return TenantLimitResponse(**value.__dict__)


@router.get("/usage")
def usage(
    auth: AuthContext = Depends(require_scope("usage:read")),
    session: Session = Depends(get_db),
) -> dict[str, int | str]:
    return _service(session).usage(auth.organization_id)


@router.get("/limits", response_model=TenantLimitResponse)
def limits(
    auth: AuthContext = Depends(require_scope("limits:read")),
    session: Session = Depends(get_db),
) -> TenantLimitResponse:
    return _limits(_service(session).limits(auth.organization_id))


@router.put("/admin/organizations/{organization_id}/limits", response_model=TenantLimitResponse)
def set_limits(
    organization_id: UUID,
    body: TenantLimitRequest,
    request: Request,
    auth: AuthContext = Depends(require_scope("organization_limits:manage")),
    session: Session = Depends(get_db),
) -> TenantLimitResponse:
    # Tenant admin keys remain organization-bound. Platform-wide support overrides require a future
    # identity provider/operator control plane, not a header-controlled escape hatch.
    if organization_id != auth.organization_id:
        raise HTTPException(403, "organization does not match the API key")
    try:
        updated = _service(session).set_limits(
            organization_id, TenantLimits(**body.model_dump()), auth.key_id
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    write_audit(
        session,
        action="tenant_limits_changed",
        outcome="accepted",
        request_id=getattr(request.state, "request_id", "unknown"),
        organization_id=organization_id,
        detail=f"tier={updated.tier} events_per_second={updated.monitoring_events_per_second}",
    )
    return _limits(updated)


@router.get("/admin/capacity/status")
def capacity_status(
    auth: AuthContext = Depends(require_scope("capacity:read")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    service = _service(session)
    queue = service.queue_snapshot()
    return {"queue": queue.__dict__, "recommendations": service.recommendations()}


@router.get("/admin/capacity/queues")
def capacity_queues(
    auth: AuthContext = Depends(require_scope("capacity:read")),
    session: Session = Depends(get_db),
) -> list[dict[str, object]]:
    return [_service(session).queue_snapshot().__dict__]


@router.get("/admin/capacity/tenants")
def capacity_tenants(
    auth: AuthContext = Depends(require_scope("capacity:read")),
    session: Session = Depends(get_db),
) -> list[dict[str, object]]:
    return list(_service(session).top_tenants())


@router.get("/admin/capacity/recommendations")
def capacity_recommendations(
    auth: AuthContext = Depends(require_scope("capacity:read")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    return _service(session).recommendations()


@router.get("/admin/performance/runs", response_model=list[PerformanceRunResponse])
def performance_runs(
    auth: AuthContext = Depends(require_scope("performance_runs:read")),
    session: Session = Depends(get_db),
) -> list[PerformanceRunResponse]:
    rows = session.scalars(
        select(PerformanceRunRecord).order_by(PerformanceRunRecord.created_at.desc()).limit(100)
    ).all()
    return [_run(row) for row in rows]


@router.get("/admin/performance/runs/{run_id}", response_model=PerformanceRunResponse)
def performance_run(
    run_id: UUID,
    auth: AuthContext = Depends(require_scope("performance_runs:read")),
    session: Session = Depends(get_db),
) -> PerformanceRunResponse:
    row = session.get(PerformanceRunRecord, run_id)
    if row is None:
        raise HTTPException(404, "performance run not found")
    return _run(row)


def _run(row: PerformanceRunRecord) -> PerformanceRunResponse:
    import json

    return PerformanceRunResponse(
        id=row.id,
        methodology_version=row.methodology_version,
        code_revision=row.code_revision,
        infrastructure=json.loads(row.infrastructure),
        workload=json.loads(row.workload),
        results=json.loads(row.results),
        status=row.status,
    )
