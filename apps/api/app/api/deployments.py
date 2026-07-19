# Purpose: HTTP surface for decoy deployment approval + lifecycle.
# Responsibilities: create/list/read deployments and previews; submit, approve, reject, deploy,
#   retire, and rollback with organization scoping, per-action permission, state-transition checks,
#   separation-of-duties, safe errors, audit, and job idempotency. It holds no GitHub logic — writes
#   run asynchronously via enqueued jobs. Dependencies: repositories, preview, settings, auth.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.dependencies import get_db
from app.models.domain.deployment import (
    DeploymentPreview,
    DeploymentStatus,
    InvalidTransitionError,
)
from app.repositories.artifacts import ArtifactRepository
from app.repositories.deployments import (
    DeploymentNotFoundError,
    DeploymentRepository,
    new_correlation_id,
)
from app.security import require_scope
from app.services.api_keys import AuthContext
from app.services.deployment.policy import PathPolicy
from app.services.deployment.preview import PreviewError, build_preview

router = APIRouter(prefix="/decoy-deployments", tags=["decoy-deployments"])


# ---- schemas -------------------------------------------------------------------------------------


class CreateDeploymentRequest(BaseModel):
    repository_id: UUID
    decoy_plan_id: UUID
    base_branch: str = Field(default="main", min_length=1, max_length=255)
    base_commit_sha: str = Field(min_length=1, max_length=64)


class DecisionRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


class DeploymentSummary(BaseModel):
    id: UUID
    repository_id: UUID
    decoy_plan_id: UUID
    status: str
    target_branch: str
    base_commit_sha: str
    pull_request_number: int | None
    pull_request_url: str | None
    monitoring_activated: bool
    expires_at: datetime | None
    failure_code: str | None
    safe_failure_message: str | None
    created_at: datetime
    updated_at: datetime


class AuditEntry(BaseModel):
    event_type: str
    request_id: str
    safe_metadata: str
    created_at: datetime


def _summary(record) -> DeploymentSummary:  # type: ignore[no-untyped-def]
    return DeploymentSummary(
        id=record.id,
        repository_id=record.repository_id,
        decoy_plan_id=record.decoy_plan_id,
        status=record.status,
        target_branch=record.target_branch,
        base_commit_sha=record.base_commit_sha,
        pull_request_number=record.pull_request_number,
        pull_request_url=record.pull_request_url,
        monitoring_activated=record.monitoring_activated_at is not None,
        expires_at=record.expires_at,
        failure_code=record.failure_code,
        safe_failure_message=record.safe_failure_message,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


# ---- helpers -------------------------------------------------------------------------------------


def _repo(session: Session) -> DeploymentRepository:
    return DeploymentRepository(session)


def _require_enabled(settings: Settings) -> None:
    if not settings.decoy_deployment_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "decoy deployment is not enabled")


def _get(repo: DeploymentRepository, auth: AuthContext, deployment_id: UUID):  # type: ignore[no-untyped-def]
    try:
        return repo.get(auth.organization_id, deployment_id)
    except DeploymentNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "deployment not found") from None


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _transition(repo: DeploymentRepository, record, target: DeploymentStatus, **fields):  # type: ignore[no-untyped-def]
    try:
        repo.transition(record, target, **fields)
    except InvalidTransitionError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None


# ---- endpoints -----------------------------------------------------------------------------------


@router.post("", response_model=DeploymentSummary, status_code=status.HTTP_201_CREATED)
def create_deployment(
    body: CreateDeploymentRequest,
    request: Request,
    auth: AuthContext = Depends(require_scope("decoy_deployments:create")),
    session: Session = Depends(get_db),
) -> DeploymentSummary:
    settings = get_settings()
    _require_enabled(settings)
    artifacts = ArtifactRepository(session, settings.max_artifact_bytes)
    loaded = artifacts.get_decoy_plan(auth.organization_id, body.decoy_plan_id)
    if loaded is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "decoy plan not found")
    _, plan = loaded
    reports = artifacts.reports_for_decoy_plan(auth.organization_id, body.decoy_plan_id)
    repo = _repo(session)
    expires_at = datetime.now(UTC) + timedelta(days=settings.decoy_default_expiry_days)
    record = repo.create(
        organization_id=auth.organization_id,
        repository_id=body.repository_id,
        decoy_plan_id=body.decoy_plan_id,
        validation_decision="accept",
        requested_by_actor_id=auth.key_id,
        target_branch="main",
        source_branch=body.base_branch,
        base_commit_sha=body.base_commit_sha,
        expires_at=expires_at,
    )
    try:
        preview, contents = build_preview(
            deployment_id=record.id,
            repository_id=body.repository_id,
            base_branch=body.base_branch,
            base_commit_sha=body.base_commit_sha,
            target_branch=f"deceptiforge/decoy-{record.id}",
            plan=plan,
            reports=reports,
            policy=PathPolicy.from_settings(settings),
            expires_at=expires_at,
        )
    except PreviewError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from None
    repo.set_preview(record, preview, contents)
    repo.add_audit(
        organization_id=auth.organization_id, deployment_id=record.id, actor_id=auth.key_id,
        event_type="deployment_created", request_id=_request_id(request),
    )
    repo.add_audit(
        organization_id=auth.organization_id, deployment_id=record.id, actor_id=auth.key_id,
        event_type="preview_generated", request_id=_request_id(request),
        safe_metadata=f"files={preview.changed_files}",
    )
    return _summary(record)


@router.get("", response_model=list[DeploymentSummary])
def list_deployments(
    auth: AuthContext = Depends(require_scope("decoy_deployments:read")),
    session: Session = Depends(get_db),
) -> list[DeploymentSummary]:
    _require_enabled(get_settings())
    return [_summary(record) for record in _repo(session).list(auth.organization_id)]


@router.get("/{deployment_id}", response_model=DeploymentSummary)
def get_deployment(
    deployment_id: UUID,
    auth: AuthContext = Depends(require_scope("decoy_deployments:read")),
    session: Session = Depends(get_db),
) -> DeploymentSummary:
    _require_enabled(get_settings())
    return _summary(_get(_repo(session), auth, deployment_id))


@router.get("/{deployment_id}/preview", response_model=DeploymentPreview)
def get_preview(
    deployment_id: UUID,
    auth: AuthContext = Depends(require_scope("decoy_deployments:read")),
    session: Session = Depends(get_db),
) -> DeploymentPreview:
    _require_enabled(get_settings())
    repo = _repo(session)
    preview = repo.load_preview(_get(repo, auth, deployment_id))
    if preview is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no preview generated")
    return preview


@router.get("/{deployment_id}/audit", response_model=list[AuditEntry])
def get_audit(
    deployment_id: UUID,
    auth: AuthContext = Depends(require_scope("decoy_deployments:read")),
    session: Session = Depends(get_db),
) -> list[AuditEntry]:
    _require_enabled(get_settings())
    repo = _repo(session)
    _get(repo, auth, deployment_id)
    return [
        AuditEntry(
            event_type=event.event_type, request_id=event.request_id,
            safe_metadata=event.safe_metadata, created_at=event.created_at,
        )
        for event in repo.audit_events(deployment_id)
    ]


@router.post("/{deployment_id}/submit", response_model=DeploymentSummary)
def submit_deployment(
    deployment_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_scope("decoy_deployments:create")),
    session: Session = Depends(get_db),
) -> DeploymentSummary:
    _require_enabled(get_settings())
    repo = _repo(session)
    record = _get(repo, auth, deployment_id)
    _transition(repo, record, DeploymentStatus.AWAITING_APPROVAL)
    repo.add_audit(
        organization_id=auth.organization_id, deployment_id=deployment_id, actor_id=auth.key_id,
        event_type="submitted", request_id=_request_id(request),
    )
    return _summary(record)


@router.post("/{deployment_id}/approve", response_model=DeploymentSummary)
def approve_deployment(
    deployment_id: UUID,
    body: DecisionRequest,
    request: Request,
    auth: AuthContext = Depends(require_scope("decoy_deployments:approve")),
    session: Session = Depends(get_db),
) -> DeploymentSummary:
    settings = get_settings()
    _require_enabled(settings)
    repo = _repo(session)
    record = _get(repo, auth, deployment_id)
    # Separation of duties: the requester may not approve their own deployment when enabled and the
    # actor identities are known.
    if (
        settings.require_separate_deployment_approver
        and auth.key_id is not None
        and record.requested_by_actor_id is not None
        and auth.key_id == record.requested_by_actor_id
    ):
        repo.add_audit(
            organization_id=auth.organization_id, deployment_id=deployment_id, actor_id=auth.key_id,
            event_type="permission_denied", request_id=_request_id(request),
            safe_metadata="separation_of_duties",
        )
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "a separate actor must approve this deployment"
        )
    _transition(repo, record, DeploymentStatus.APPROVED, approved_by_actor_id=auth.key_id)
    repo.add_approval(
        organization_id=auth.organization_id, deployment_id=deployment_id, actor_id=auth.key_id,
        decision="approved", comment=body.comment,
    )
    repo.add_audit(
        organization_id=auth.organization_id, deployment_id=deployment_id, actor_id=auth.key_id,
        event_type="approved", request_id=_request_id(request),
    )
    return _summary(record)


@router.post("/{deployment_id}/reject", response_model=DeploymentSummary)
def reject_deployment(
    deployment_id: UUID,
    body: DecisionRequest,
    request: Request,
    auth: AuthContext = Depends(require_scope("decoy_deployments:approve")),
    session: Session = Depends(get_db),
) -> DeploymentSummary:
    _require_enabled(get_settings())
    repo = _repo(session)
    record = _get(repo, auth, deployment_id)
    _transition(repo, record, DeploymentStatus.REJECTED)
    repo.add_approval(
        organization_id=auth.organization_id, deployment_id=deployment_id, actor_id=auth.key_id,
        decision="rejected", comment=body.comment,
    )
    repo.add_audit(
        organization_id=auth.organization_id, deployment_id=deployment_id, actor_id=auth.key_id,
        event_type="rejected", request_id=_request_id(request),
    )
    return _summary(record)


def _lifecycle_action(
    session: Session,
    auth: AuthContext,
    request: Request,
    deployment_id: UUID,
    *,
    target: DeploymentStatus,
    job_type: str,
    event: str,
) -> DeploymentSummary:
    _require_enabled(get_settings())
    repo = _repo(session)
    record = _get(repo, auth, deployment_id)
    _transition(repo, record, target)
    # Lifecycle jobs may follow one another on the same deployment; clear any prior job of this type
    # so a legitimate later action can enqueue, while a duplicate concurrent request is deduped.
    repo.clear_job(deployment_id, job_type)
    repo.enqueue_job(
        organization_id=auth.organization_id, deployment_id=deployment_id, job_type=job_type,
        correlation_id=new_correlation_id(),
    )
    repo.add_audit(
        organization_id=auth.organization_id, deployment_id=deployment_id, actor_id=auth.key_id,
        event_type=event, request_id=_request_id(request),
    )
    return _summary(record)


@router.post("/{deployment_id}/deploy", response_model=DeploymentSummary)
def deploy_deployment(
    deployment_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_scope("decoy_deployments:execute")),
    session: Session = Depends(get_db),
) -> DeploymentSummary:
    return _lifecycle_action(
        session, auth, request, deployment_id,
        target=DeploymentStatus.DEPLOYING, job_type="execute", event="deployment_started",
    )


@router.post("/{deployment_id}/retire", response_model=DeploymentSummary)
def retire_deployment(
    deployment_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_scope("decoy_deployments:retire")),
    session: Session = Depends(get_db),
) -> DeploymentSummary:
    return _lifecycle_action(
        session, auth, request, deployment_id,
        target=DeploymentStatus.RETIRING, job_type="retire", event="retirement_started",
    )


@router.post("/{deployment_id}/rollback", response_model=DeploymentSummary)
def rollback_deployment(
    deployment_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_scope("decoy_deployments:rollback")),
    session: Session = Depends(get_db),
) -> DeploymentSummary:
    return _lifecycle_action(
        session, auth, request, deployment_id,
        target=DeploymentStatus.ROLLBACK_PENDING, job_type="rollback", event="rollback_started",
    )
