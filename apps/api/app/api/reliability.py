# Purpose: highly-privileged admin surface for reliability + disaster recovery.
# Responsibilities: report region/dependency status, backups + restore drills, run a modeled restore
#   drill (records achieved RPO/RTO + checksummed report), read failover events, and drive the
#   controlled failover state machine with separation of duties (request vs approve by different
#   operators). Never exposes infrastructure credentials or raw provider responses. Org-independent
#   operational records; scope-gated. Dependencies: services, repository, settings, auth.
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.dependencies import get_db
from app.models.domain.reliability import RECOVERY_OBJECTIVES, DataClass, FailoverState
from app.repositories.reliability import ReliabilityRepository, current_migration_head
from app.security import require_scope
from app.services.api_keys import AuthContext
from app.services.metrics import emit
from app.services.reliability import backup_meta, degraded, fencing, objectives, restore_verify
from app.services.reliability.failover import FailoverError, FailoverService

router = APIRouter(tags=["reliability"], prefix="/admin/reliability")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _repo(session: Session) -> ReliabilityRepository:
    return ReliabilityRepository(session)


@router.get("/status")
def status_view(
    auth: AuthContext = Depends(require_scope("reliability:read")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    repo = _repo(session)
    identity = fencing.runtime_identity(settings)
    latest_drill = repo.latest_drill()
    return {
        "region": identity.model_dump(mode="json"),
        "failover_state": repo.current_state().value,
        "recovery_objectives": {
            k.value: v.model_dump(mode="json") for k, v in RECOVERY_OBJECTIVES.items()
        },
        "latest_verified_restore": (
            {
                "backup_identifier": latest_drill.backup_identifier,
                "passed": latest_drill.passed,
                "achieved_rpo_minutes": latest_drill.achieved_rpo_minutes,
                "achieved_rto_minutes": latest_drill.achieved_rto_minutes,
                "created_at": latest_drill.created_at.isoformat(),
            }
            if latest_drill
            else None
        ),
        "maintenance_mode": settings.maintenance_mode,
    }


@router.get("/dependencies")
def dependencies_view(
    auth: AuthContext = Depends(require_scope("reliability:read")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    return degraded.dependency_status(session, get_settings())


@router.get("/backups")
def backups_view(
    auth: AuthContext = Depends(require_scope("backups:read")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    meta = backup_meta.backup_metadata(session, backup_identifier="current-schema")
    backup_meta.assert_no_secrets(meta)  # never leak a secret through the inventory
    return meta


@router.get("/restore-drills")
def list_drills(
    auth: AuthContext = Depends(require_scope("reliability:read")),
    session: Session = Depends(get_db),
) -> list[dict[str, object]]:
    return [
        {
            "id": str(d.id), "backup_identifier": d.backup_identifier, "passed": d.passed,
            "achieved_rpo_minutes": d.achieved_rpo_minutes,
            "achieved_rto_minutes": d.achieved_rto_minutes, "checksum": d.checksum,
            "created_at": d.created_at.isoformat(),
        }
        for d in _repo(session).drills()
    ]


class RunDrillRequest(BaseModel):
    backup_identifier: str = Field(min_length=1, max_length=128)
    recovery_point: datetime
    last_durable_write: datetime | None = None


@router.post("/restore-drills")
def run_drill(
    body: RunDrillRequest, request: Request,
    auth: AuthContext = Depends(require_scope("restore_drills:run")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    if not settings.restore_drill_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "restore drills are not enabled")
    started = datetime.now(UTC)
    head = current_migration_head()
    checks = restore_verify.verify(session, settings, expected_migration=head)
    finished = datetime.now(UTC)
    rpo = objectives.achieved_rpo_minutes(
        body.last_durable_write or body.recovery_point, body.recovery_point
    )
    rto = objectives.achieved_rto_minutes(started, finished)
    report = restore_verify.build_report(
        drill_id="pending", backup_identifier=body.backup_identifier,
        recovery_point=body.recovery_point, started_at=started, finished_at=finished,
        achieved_rpo_minutes=rpo, achieved_rto_minutes=rto, migration_revision=head, checks=checks,
    )
    repo = _repo(session)
    drill = repo.record_drill(
        report, deployment_region=settings.deployment_region, requested_by=auth.key_id
    )
    repo.add_audit(
        event_type="restore_drill", request_id=_request_id(request),
        deployment_region=settings.deployment_region, actor_id=auth.key_id,
        safe_metadata=f"passed={report.passed}",
    )
    emit("reliability_restore_drill", passed=report.passed, rpo=rpo, rto=rto)
    return {
        "id": str(drill.id), "passed": report.passed, "achieved_rpo_minutes": rpo,
        "achieved_rto_minutes": rto,
        "checks": [c.model_dump(mode="json") for c in report.checks],
        "within_targets": objectives.within_targets(
            rpo=rpo, rto=rto,
            rpo_target=RECOVERY_OBJECTIVES[DataClass.CRITICAL].rpo_minutes,
            rto_target=RECOVERY_OBJECTIVES[DataClass.CRITICAL].rto_minutes,
        ),
    }


@router.get("/failover-events")
def failover_events(
    auth: AuthContext = Depends(require_scope("reliability:read")),
    session: Session = Depends(get_db),
) -> list[dict[str, object]]:
    return [
        {
            "id": str(e.id), "from_state": e.from_state, "to_state": e.to_state,
            "deployment_region": e.deployment_region, "active_region_epoch": e.active_region_epoch,
            "reason": e.reason, "created_at": e.created_at.isoformat(),
        }
        for e in _repo(session).failover_events()
    ]


class FailoverRequestBody(BaseModel):
    reason: str = Field(min_length=1, max_length=512)


@router.post("/failover/request")
def failover_request(
    body: FailoverRequestBody, request: Request,
    auth: AuthContext = Depends(require_scope("failover:request")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    repo = _repo(session)
    svc = FailoverService(repo, settings)
    try:
        state = svc.request_failover(actor_id=auth.key_id, reason=body.reason)
    except FailoverError as error:
        raise HTTPException(error.status_code, error.message) from None
    repo.add_audit(
        event_type="failover_requested", request_id=_request_id(request),
        deployment_region=settings.deployment_region, actor_id=auth.key_id,
    )
    return {"failover_state": state.value}


@router.post("/failover/approve")
def failover_approve(
    body: FailoverRequestBody, request: Request,
    auth: AuthContext = Depends(require_scope("failover:approve")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    repo = _repo(session)
    svc = FailoverService(repo, settings)
    try:
        state = svc.approve_failover(actor_id=auth.key_id, reason=body.reason)
    except FailoverError as error:
        raise HTTPException(error.status_code, error.message) from None
    repo.add_audit(
        event_type="failover_approved", request_id=_request_id(request),
        deployment_region=settings.deployment_region, actor_id=auth.key_id,
    )
    return {"failover_state": state.value}


class AdvanceBody(BaseModel):
    target: FailoverState
    reason: str = Field(min_length=1, max_length=512)


@router.post("/failover/advance")
def failover_advance(
    body: AdvanceBody, request: Request,
    auth: AuthContext = Depends(require_scope("failback:manage")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    repo = _repo(session)
    svc = FailoverService(repo, settings)
    try:
        state = svc.advance(body.target, actor_id=auth.key_id, reason=body.reason)
    except FailoverError as error:
        raise HTTPException(error.status_code, error.message) from None
    repo.add_audit(
        event_type="failover_advanced", request_id=_request_id(request),
        deployment_region=settings.deployment_region, actor_id=auth.key_id,
        safe_metadata=state.value,
    )
    return {"failover_state": state.value}
