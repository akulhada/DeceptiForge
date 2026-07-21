# Purpose: HTTP surface for the restricted judge workspace at the root route.
# Responsibilities: resolve the caller's TTL-bound sandbox from their authenticated organization,
#   enforce per-session budgets, run ONLY deterministic analysis over the bounded signals contract,
#   and reset the sandbox's own records. Never scans a path, never opens a connector, never touches
#   another organization: the sandbox organization comes from the resolved session row, never from
#   the request body.
# Dependencies: judge sandbox + quota services, the shared analysis contract, auth, settings.
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.dependencies import get_db
from app.models.domain.analysis_preview import AnalysisPreviewResponse
from app.models.domain.analysis_signals import (
    MAX_TOTAL_PATHS,
    RepositorySignals,
    total_representative_paths,
)
from app.security import require_scope
from app.services.analysis_lab import AnalysisPreviewService
from app.services.analysis_lab.scenarios import load_scenarios
from app.services.api_keys import AuthContext
from app.services.judge_interaction import JudgeInteractionService
from app.services.judge_quota import (
    ANALYZE,
    EXPORT,
    INTERACT,
    RESET,
    JudgeQuotaService,
    QuotaDenial,
)
from app.services.judge_sandbox import (
    JudgeSandboxService,
    SandboxError,
    SandboxNamespace,
    SandboxResetService,
)
from app.services.metrics import emit

router = APIRouter(prefix="/api/v1/judge", tags=["judge"])

# The same deterministic engines the Analysis Lab uses. Reused rather than reimplemented so a judge
# sees the real product behaviour, not a parallel code path built to look good.
_analysis = AnalysisPreviewService()


class JudgeAnalyzeRequest(BaseModel):
    """Bounded structured signals only.

    `extra="forbid"`: a judge may not smuggle an unmodelled field such as a repository URL, a
    filesystem path to scan, or connector credentials. Path-like values inside the signals contract
    are descriptive metadata; nothing here is ever opened.
    """

    model_config = ConfigDict(extra="forbid")

    signals: RepositorySignals
    scenario_id: str | None = Field(default=None, max_length=64)


class QuotaView(BaseModel):
    used: int
    limit: int
    remaining: int


class ScenarioView(BaseModel):
    id: str
    name: str
    description: str


class WorkspaceView(BaseModel):
    """Everything the workspace UI needs, all derived from backend state."""

    organization_id: str
    session_id: str
    environment: str
    label: str
    expires_at: str
    quotas: dict[str, QuotaView]
    scenarios: list[ScenarioView]


class ResetResult(BaseModel):
    deleted: dict[str, int]
    quotas: dict[str, QuotaView]


def _namespace_of(record) -> SandboxNamespace:  # type: ignore[no-untyped-def]
    """Build the namespace from the RESOLVED sandbox row, never from anything client-supplied."""
    return SandboxNamespace(
        environment=record.environment,
        organization_id=record.organization_id,
        session_id=record.session_id,
    )


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _resolve(session: Session, auth: AuthContext):  # type: ignore[no-untyped-def]
    """Resolve the caller's sandbox from their AUTHENTICATED organization.

    The organization is never read from the request body or a query parameter, so a judge cannot
    address another judge's sandbox by guessing an id — the only sandbox reachable is the one their
    credential is bound to.
    """
    try:
        return JudgeSandboxService(session, get_settings()).resolve(auth.organization_id)
    except SandboxError as error:
        raise HTTPException(error.status_code, error.message) from error


def _deny(denial: QuotaDenial) -> HTTPException:
    headers = (
        {"Retry-After": str(denial.retry_after_seconds)}
        if denial.retry_after_seconds is not None
        else None
    )
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, denial.detail, headers=headers)


def _quota_view(quotas: dict[str, object]) -> dict[str, QuotaView]:
    return {
        action: QuotaView(used=state.used, limit=state.limit, remaining=state.remaining)  # type: ignore[attr-defined]
        for action, state in quotas.items()
    }


@router.get("/workspace", response_model=WorkspaceView)
def workspace(
    request: Request,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_scope("judge:workspace")),
) -> WorkspaceView:
    """The judge's own session state. 410 once the sandbox has expired."""
    record = _resolve(session, auth)
    quotas = JudgeQuotaService(get_settings()).state(record)
    return WorkspaceView(
        organization_id=str(record.organization_id),
        session_id=str(record.session_id),
        environment=record.environment,
        label=record.label,
        expires_at=record.expires_at.isoformat(),
        quotas=_quota_view(dict(quotas)),
        scenarios=[
            ScenarioView(id=s.scenario_id, name=s.name, description=s.description)
            for s in load_scenarios()
        ],
    )


@router.post("/analyze", response_model=AnalysisPreviewResponse)
def analyze(
    payload: JudgeAnalyzeRequest,
    request: Request,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_scope("judge:analyze")),
) -> AnalysisPreviewResponse:
    """Deterministic analysis over approved structured signals. Opens nothing, calls no model."""
    settings = get_settings()
    record = _resolve(session, auth)
    quota = JudgeQuotaService(settings)
    request_id = _request_id(request)
    org = str(record.organization_id)

    denial = quota.check(record, ANALYZE)
    if denial is not None:
        emit("judge_quota_denied", organization_id=org, request_id=request_id, action=ANALYZE)
        raise _deny(denial)

    # Aggregate bound enforced before any analysis runs; per-collection bounds live in the contract.
    if total_representative_paths(payload.signals) > MAX_TOTAL_PATHS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"too many representative paths (limit {MAX_TOTAL_PATHS})",
        )

    quota.consume(record, ANALYZE)
    session.commit()
    emit("judge_analysis", organization_id=org, request_id=request_id)
    # No calibration is passed: a judge sees the deterministic engines' own output, not a tenant's
    # approved weights. Nothing about this call reads or writes learning state.
    return _analysis.analyze(
        payload.signals,
        organization_id=org,
        request_id=request_id,
        scenario_id=payload.scenario_id,
    )


@router.post("/reset", response_model=ResetResult)
def reset(
    request: Request,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_scope("judge:reset")),
) -> ResetResult:
    """Clear this sandbox's own generated records.

    Preserves authentication, the organization assignment and the quota accounting: a reset restores
    the sandbox's data, never its budget.
    """
    settings = get_settings()
    record = _resolve(session, auth)
    quota = JudgeQuotaService(settings)
    request_id = _request_id(request)
    org = str(record.organization_id)

    denial = quota.check(record, RESET)
    if denial is not None:
        emit("judge_quota_denied", organization_id=org, request_id=request_id, action=RESET)
        raise _deny(denial)

    deleted = SandboxResetService(session).reset(_namespace_of(record))
    quota.consume(record, RESET)
    session.commit()
    emit("judge_reset", organization_id=org, request_id=request_id)
    return ResetResult(deleted=deleted, quotas=_quota_view(dict(quota.state(record))))


class InteractionResult(BaseModel):
    """What the real pipeline produced. Every field is read back from persisted state."""

    trace_identifier: str
    event_recorded: bool
    alert_id: str | None
    incident_id: str | None
    quotas: dict[str, QuotaView]


class ExportResult(BaseModel):
    """A safe, self-describing snapshot of the judge's own sandbox."""

    organization_id: str
    session_id: str
    environment: str
    exported_at: str
    repositories: int
    decoy_assets: int
    monitoring_events: int
    alerts: int
    incidents: int
    quotas: dict[str, QuotaView]


@router.post("/interact", response_model=InteractionResult)
def interact(
    request: Request,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_scope("judge:interact")),
) -> InteractionResult:
    """Trigger ONE controlled interaction against a decoy in this sandbox.

    The event goes through the ordinary monitoring pipeline, which is what creates the alert and
    schedules reconstruction. Nothing is inserted directly into alerts or incidents: if the pipeline
    would not have produced them, the judge does not see them. The target is chosen server-side from
    the sandbox's own accepted decoys — the request carries no identifiers at all, so a judge cannot
    aim an interaction at another organization's asset.
    """
    settings = get_settings()
    record = _resolve(session, auth)
    quota = JudgeQuotaService(settings)
    request_id = _request_id(request)
    org = str(record.organization_id)

    denial = quota.check(record, INTERACT)
    if denial is not None:
        emit("judge_quota_denied", organization_id=org, request_id=request_id, action=INTERACT)
        raise _deny(denial)

    result = JudgeInteractionService(session).interact(_namespace_of(record))
    if result is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "this sandbox has no accepted decoy to interact with; reset it and try again",
        )

    quota.consume(record, INTERACT)
    session.commit()
    emit("judge_interaction", organization_id=org, request_id=request_id)
    return InteractionResult(
        trace_identifier=result.trace_identifier,
        event_recorded=result.event_recorded,
        alert_id=str(result.alert_id) if result.alert_id else None,
        incident_id=str(result.incident_id) if result.incident_id else None,
        quotas=_quota_view(dict(quota.state(record))),
    )


@router.get("/export", response_model=ExportResult)
def export(
    request: Request,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_scope("judge:export")),
) -> ExportResult:
    """Export counts describing this sandbox's own state.

    Deliberately aggregate: the export carries no decoy content, no trace tokens and no event
    payloads, so a judge cannot walk away with material that would help defeat a real deployment.
    """
    settings = get_settings()
    record = _resolve(session, auth)
    quota = JudgeQuotaService(settings)
    request_id = _request_id(request)
    org = str(record.organization_id)

    denial = quota.check(record, EXPORT)
    if denial is not None:
        emit("judge_quota_denied", organization_id=org, request_id=request_id, action=EXPORT)
        raise _deny(denial)

    counts = JudgeInteractionService(session).summarize(_namespace_of(record))
    quota.consume(record, EXPORT)
    session.commit()
    emit("judge_export", organization_id=org, request_id=request_id)
    return ExportResult(
        organization_id=org,
        session_id=str(record.session_id),
        environment=record.environment,
        exported_at=datetime.now(UTC).isoformat(),
        quotas=_quota_view(dict(quota.state(record))),
        **counts,
    )
