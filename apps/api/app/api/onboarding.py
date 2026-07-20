"""Authenticated guided-activation API; all progress is derived server-side."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.dependencies import get_db
from app.security import require_scope
from app.services.api_keys import AuthContext, write_audit
from app.services.onboarding import OnboardingService

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class DetectionTestRequest(BaseModel):
    deployment_id: UUID


def _enabled(settings: Settings) -> None:
    if not settings.onboarding_enabled:
        raise HTTPException(404, "onboarding is not enabled")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _workspace_view(service: OnboardingService, organization_id: UUID) -> dict[str, object]:
    view = service.view(organization_id)
    workspace = cast(Any, view["workspace"])
    steps = cast(tuple[Any, ...], view["steps"])
    return {
        "id": str(workspace.id),
        "status": workspace.status,
        "current_phase": workspace.current_phase,
        "started_at": workspace.started_at,
        "activated_at": workspace.activated_at,
        "onboarding_version": workspace.onboarding_version,
        "activated": view["activated"],
        "steps": [
            {
                "phase": step.phase,
                "step_key": step.step_key,
                "status": step.status,
                "blocked_reason_code": step.blocked_reason_code,
                "safe_blocked_message": step.safe_blocked_message,
                "completed_at": step.completed_at,
            }
            for step in steps
        ],
    }


@router.get("")
def get_onboarding(
    auth: AuthContext = Depends(require_scope("onboarding:read")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    _enabled(settings)
    return _workspace_view(OnboardingService(session, settings), auth.organization_id)


@router.post("/start")
def start_onboarding(
    request: Request,
    auth: AuthContext = Depends(require_scope("onboarding:manage")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    _enabled(settings)
    service = OnboardingService(session, settings)
    service.start(auth.organization_id)
    write_audit(
        session,
        action="onboarding_started",
        outcome="accepted",
        request_id=_request_id(request),
        organization_id=auth.organization_id,
        detail="state-derived onboarding started",
    )
    return _workspace_view(service, auth.organization_id)


@router.post("/pause")
def pause_onboarding(
    request: Request,
    auth: AuthContext = Depends(require_scope("onboarding:manage")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    _enabled(settings)
    service = OnboardingService(session, settings)
    service.pause(auth.organization_id)
    write_audit(
        session,
        action="onboarding_paused",
        outcome="accepted",
        request_id=_request_id(request),
        organization_id=auth.organization_id,
        detail="onboarding paused",
    )
    return _workspace_view(service, auth.organization_id)


@router.post("/resume")
def resume_onboarding(
    request: Request,
    auth: AuthContext = Depends(require_scope("onboarding:manage")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    _enabled(settings)
    service = OnboardingService(session, settings)
    service.resume(auth.organization_id)
    write_audit(
        session,
        action="onboarding_resumed",
        outcome="accepted",
        request_id=_request_id(request),
        organization_id=auth.organization_id,
        detail="onboarding resumed",
    )
    return _workspace_view(service, auth.organization_id)


@router.get("/steps")
def steps(
    auth: AuthContext = Depends(require_scope("onboarding:read")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    _enabled(settings)
    return {
        "steps": _workspace_view(OnboardingService(session, settings), auth.organization_id)[
            "steps"
        ]
    }


@router.get("/recommendations")
def recommendations(
    auth: AuthContext = Depends(require_scope("onboarding:read")),
    session: Session = Depends(get_db),
) -> list[dict[str, object]]:
    settings = get_settings()
    _enabled(settings)
    return [
        {
            "id": str(r.id),
            "recommendation_type": r.recommendation_type,
            "target_surface_type": r.target_surface_type,
            "priority": r.priority,
            "expected_activation_gain": r.expected_activation_gain,
            "expected_coverage_gain": r.expected_coverage_gain,
            "implementation_effort": r.implementation_effort,
            "risk": r.risk,
            "explanation": r.explanation,
            "status": r.status,
        }
        for r in OnboardingService(session, settings).recommendations(auth.organization_id)
    ]


@router.post("/recommendations/{recommendation_id}/{decision}")
def decide_recommendation(
    recommendation_id: UUID,
    decision: str,
    request: Request,
    auth: AuthContext = Depends(require_scope("onboarding:accept_recommendation")),
    session: Session = Depends(get_db),
) -> dict[str, str]:
    settings = get_settings()
    _enabled(settings)
    if decision not in {"accept", "dismiss"}:
        raise HTTPException(404, "decision not found")
    record = OnboardingService(session, settings).decide_recommendation(
        auth.organization_id, recommendation_id, "accepted" if decision == "accept" else "dismissed"
    )
    if record is None:
        raise HTTPException(404, "recommendation not found")
    write_audit(
        session,
        action=f"onboarding_recommendation_{decision}ed",
        outcome="accepted",
        request_id=_request_id(request),
        organization_id=auth.organization_id,
        detail="safe onboarding recommendation",
    )
    return {"status": record.status}


@router.post("/detection-tests")
def create_detection_test(
    body: DetectionTestRequest,
    request: Request,
    auth: AuthContext = Depends(require_scope("onboarding:run_detection_test")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    _enabled(settings)
    if not settings.onboarding_detection_test_enabled:
        raise HTTPException(404, "controlled detection tests are not enabled")
    try:
        run = OnboardingService(session, settings).create_detection_test(
            auth.organization_id, auth.key_id, body.deployment_id
        )
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    write_audit(
        session,
        action="onboarding_detection_test_started",
        outcome="accepted",
        request_id=_request_id(request),
        organization_id=auth.organization_id,
        detail="controlled test awaits signed monitoring event",
    )
    return {
        "id": str(run.id),
        "status": run.status,
        "trace_identifier": run.trace_identifier,
        "started_at": run.started_at,
        "instructions": (
            "Touch the verified decoy through its enrolled monitor; this endpoint does not "
            "create an alert or incident."
        ),
    }


@router.get("/detection-tests/{test_id}")
def get_detection_test(
    test_id: UUID,
    auth: AuthContext = Depends(require_scope("onboarding:read")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    _enabled(settings)
    from app.models.records import DetectionTestRunRecord

    run = session.get(DetectionTestRunRecord, test_id)
    if run is None or run.organization_id != auth.organization_id:
        raise HTTPException(404, "detection test not found")
    return {
        "id": str(run.id),
        "status": run.status,
        "observed_event_id": str(run.observed_event_id) if run.observed_event_id else None,
        "alert_id": str(run.alert_id) if run.alert_id else None,
        "incident_id": str(run.incident_id) if run.incident_id else None,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "safe_failure_code": run.safe_failure_code,
    }


@router.post("/recalculate")
def recalculate(
    request: Request,
    auth: AuthContext = Depends(require_scope("onboarding:manage")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    _enabled(settings)
    service = OnboardingService(session, settings)
    service.reconcile(auth.organization_id)
    write_audit(
        session,
        action="onboarding_reconciled",
        outcome="accepted",
        request_id=_request_id(request),
        organization_id=auth.organization_id,
        detail="authoritative state reconciled",
    )
    return _workspace_view(service, auth.organization_id)
