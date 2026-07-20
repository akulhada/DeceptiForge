# Purpose: build the unified protected-surface inventory + observed controls from existing records.
# Responsibilities: enumerate repository / database / RAG / MCP / browser-AI / agent surfaces
#   organization-scoped, score each deterministically (criticality/risk/confidence), and attach the
#   controls actually present (decoy/sensor/monitoring/verification/lifecycle) with real statuses
#   from deployment + sensor state. Bounded, indexed queries; no O(n^2). GPT never contributes.
# Dependencies: records, coverage domain, scoring, settings.
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.models.domain.coverage import (
    ControlStatus,
    ControlType,
    CoverageDimension,
    InventorySurface,
    SurfaceControl,
    SurfaceType,
)
from app.models.records import (
    AgentScopePolicyRecord,
    AgentSensorRecord,
    AiTripwireDeploymentRecord,
    AlertRecord,
    BrowserAiPolicyRecord,
    DatabaseHoneyDeploymentRecord,
    DecoyDeploymentRecord,
    IncidentRecord,
    McpConnectorRecord,
    MonitorCredentialRecord,
    RagConnectorRecord,
    RepositoryRecord,
)
from app.services.coverage_engine import scoring

_SENSITIVE_WORDS = ("billing", "payment", "auth", "credential", "secret", "customer", "invoice",
                    "deploy", "env", "account")


@dataclass
class SurfaceObservation:
    surface: InventorySurface
    controls: list[SurfaceControl] = field(default_factory=list)


@dataclass(frozen=True)
class OrgCapabilities:
    has_alerting: bool
    has_incidents: bool
    has_signed_monitor: bool


def _hours_since(ts: datetime | None, now: datetime) -> float:
    if ts is None:
        return 1e9
    ts = ts if ts.tzinfo else ts.replace(tzinfo=UTC)
    return max(0.0, (now - ts).total_seconds() / 3600.0)


def _sensitivity_for(name: str) -> float:
    lower = name.lower()
    hits = sum(1 for w in _SENSITIVE_WORDS if w in lower)
    return scoring.clamp(0.4 + 0.15 * hits)


def _capabilities(session: Session, org) -> OrgCapabilities:  # type: ignore[no-untyped-def]
    has_alert = session.scalars(
        select(AlertRecord.id).where(AlertRecord.organization_id == org).limit(1)
    ).first() is not None
    has_incident = session.scalars(
        select(IncidentRecord.id).where(IncidentRecord.organization_id == org).limit(1)
    ).first() is not None
    has_monitor = session.scalars(
        select(MonitorCredentialRecord.id).where(
            MonitorCredentialRecord.organization_id == org,
            MonitorCredentialRecord.status == "active",
        ).limit(1)
    ).first() is not None
    return OrgCapabilities(has_alert, has_incident, has_monitor)


def _surface(
    surface_type: SurfaceType, ext_id: str, name: str, *, sensitivity: float, business: float,
    exposure: float, attack: float, measured: bool, freshness_hours: float,
    metadata_completeness: float,
) -> InventorySurface:
    crit = scoring.criticality(
        sensitivity=sensitivity, business_impact=business, exposure=exposure,
        attack_likelihood=attack,
    )
    conf = scoring.inventory_confidence(
        measured=measured, freshness_hours=freshness_hours,
        metadata_completeness=metadata_completeness,
    )
    return InventorySurface(
        surface_type=surface_type, external_or_resource_id=ext_id[:512], display_name=name[:256],
        criticality=crit, exposure_score=scoring.clamp(exposure),
        sensitivity_score=scoring.clamp(sensitivity), attack_likelihood=scoring.clamp(attack),
        business_impact=scoring.clamp(business), coverage_requirement=1.0,
        risk_weight=scoring.risk_weight(crit, 1.0), inventory_confidence=conf, status="known",
        explanation=(
            f"criticality {crit:.2f} from sensitivity {sensitivity:.2f}, business {business:.2f}, "
            f"exposure {exposure:.2f}, attacker likelihood {attack:.2f}"
        ),
    )


def _decoy_status(status: str, expires_at: datetime | None, now: datetime) -> ControlStatus:
    if status in ("failed", "verification_failed", "failed_activation", "drift_detected"):
        return ControlStatus.FAILED
    if status in ("retired", "rolled_back", "cancelled", "rejected"):
        return ControlStatus.INACTIVE
    if status == "expired":
        return ControlStatus.EXPIRED
    if expires_at is not None:
        exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
        if exp < now:
            return ControlStatus.EXPIRED
    if status in ("deployed", "active"):
        return ControlStatus.ACTIVE
    return ControlStatus.INACTIVE


def build_inventory(
    session: Session, organization_id: UUID, settings: Settings, *, now: datetime | None = None
) -> list[SurfaceObservation]:
    now = now or datetime.now(UTC)
    caps = _capabilities(session, organization_id)
    vmax = settings.coverage_verification_max_age_hours
    observations: list[SurfaceObservation] = []

    def add_capability_controls(obs: SurfaceObservation, has_active_decoy: bool) -> None:
        # Alerting/incident/identity are org-wide capabilities applied only where a live sensor
        # exists (a detection must be possible before it can become an alert/incident).
        if not has_active_decoy:
            return
        if caps.has_signed_monitor:
            obs.controls.append(_control(
                ControlType.MONITORING, "signed-monitor", ControlStatus.ACTIVE,
                CoverageDimension.IDENTITY, 0.9, now,
            ))
        if caps.has_alerting:
            obs.controls.append(_control(
                ControlType.ALERTING, "alert-pipeline", ControlStatus.ACTIVE,
                CoverageDimension.ALERTING, 0.85, now,
            ))
        if caps.has_incidents:
            obs.controls.append(_control(
                ControlType.INCIDENT_RESPONSE, "incident-recon", ControlStatus.ACTIVE,
                CoverageDimension.INCIDENT, 0.8, now,
            ))

    org = organization_id
    add = add_capability_controls
    observations += _repository_surfaces(session, org, now, vmax, add)  # type: ignore[no-untyped-call]
    observations += _database_surfaces(session, org, now, vmax, add)  # type: ignore[no-untyped-call]
    observations += _rag_mcp_surfaces(session, org, now, vmax, add)  # type: ignore[no-untyped-call]
    observations += _browser_surfaces(session, org, now, add)  # type: ignore[no-untyped-call]
    observations += _agent_surfaces(session, org, now, add)  # type: ignore[no-untyped-call]
    return observations


def _control(
    control_type: ControlType, ref: str, status: ControlStatus, dimension: CoverageDimension,
    effectiveness: float, now: datetime, *, verified_at: datetime | None = None,
) -> SurfaceControl:
    return SurfaceControl(
        control_type=control_type, control_reference_id=ref[:128], status=status,
        effectiveness_score=effectiveness if status == ControlStatus.ACTIVE else 0.0,
        confidence=0.9, last_verified_at=verified_at, dimension=dimension,
    )


def _repository_surfaces(session, org, now, vmax, add_caps):  # type: ignore[no-untyped-def]
    out: list[SurfaceObservation] = []
    repos = session.scalars(
        select(RepositoryRecord).where(RepositoryRecord.organization_id == org)
    ).all()
    for repo in repos:
        surface = _surface(
            SurfaceType.REPOSITORY, str(repo.id), repo.name,
            sensitivity=_sensitivity_for(repo.name), business=0.7, exposure=0.6, attack=0.6,
            measured=True, freshness_hours=_hours_since(repo.created_at, now),
            metadata_completeness=0.7,
        )
        obs = SurfaceObservation(surface)
        deployments = session.scalars(
            select(DecoyDeploymentRecord).where(
                DecoyDeploymentRecord.organization_id == org,
                DecoyDeploymentRecord.repository_id == repo.id,
            )
        ).all()
        has_active = False
        for d in deployments:
            status = _decoy_status(d.status, d.expires_at, now)
            eff = scoring.control_effectiveness(
                status=status, believability=0.7, verified_at=d.deployed_at, now=now,
                verification_max_age_hours=vmax,
            )
            obs.controls.append(SurfaceControl(
                control_type=ControlType.DECOY, control_reference_id=str(d.id)[:128],
                status=status, effectiveness_score=eff, confidence=0.9,
                last_verified_at=d.deployed_at, dimension=CoverageDimension.PLACEMENT,
            ))
            if status == ControlStatus.ACTIVE:
                has_active = True
                if d.monitoring_activated_at is not None:
                    obs.controls.append(_control(
                        ControlType.SENSOR, f"repo-sensor:{d.id}", ControlStatus.ACTIVE,
                        CoverageDimension.SENSOR, 0.85, now, verified_at=d.monitoring_activated_at,
                    ))
                    obs.controls.append(_control(
                        ControlType.MONITORING, f"repo-health:{d.id}", ControlStatus.ACTIVE,
                        CoverageDimension.HEALTH, 0.85, now,
                    ))
                if d.expires_at is not None or d.retired_at is not None:
                    obs.controls.append(_control(
                        ControlType.DECOY, f"repo-lifecycle:{d.id}", ControlStatus.ACTIVE,
                        CoverageDimension.LIFECYCLE, 0.8, now,
                    ))
        add_caps(obs, has_active)
        out.append(obs)
    return out


def _database_surfaces(session, org, now, vmax, add_caps):  # type: ignore[no-untyped-def]
    out: list[SurfaceObservation] = []
    # Surface per (connector, table) that has a honey deployment.
    rows = session.scalars(
        select(DatabaseHoneyDeploymentRecord).where(
            DatabaseHoneyDeploymentRecord.organization_id == org
        )
    ).all()
    by_key: dict[str, list] = {}  # type: ignore[type-arg]
    for r in rows:
        by_key.setdefault(f"{r.connector_id}:{r.target_schema}.{r.target_table}", []).append(r)
    for key, deployments in by_key.items():
        name = key.split(":", 1)[1]
        surface = _surface(
            SurfaceType.DATABASE, key, name, sensitivity=_sensitivity_for(name), business=0.8,
            exposure=0.5, attack=0.6, measured=True,
            freshness_hours=_hours_since(deployments[0].created_at, now),
            metadata_completeness=0.8,
        )
        obs = SurfaceObservation(surface)
        has_active = False
        for d in deployments:
            status = _decoy_status(d.status, d.expires_at, now)
            eff = scoring.control_effectiveness(
                status=status, believability=0.75, verified_at=d.deployed_at, now=now,
                verification_max_age_hours=vmax,
            )
            obs.controls.append(SurfaceControl(
                control_type=ControlType.DECOY, control_reference_id=str(d.id)[:128], status=status,
                effectiveness_score=eff, confidence=0.9, last_verified_at=d.deployed_at,
                dimension=CoverageDimension.PLACEMENT,
            ))
            if status == ControlStatus.ACTIVE:
                has_active = True
                if d.monitoring_activated_at is not None:
                    obs.controls.append(_control(
                        ControlType.SENSOR, f"db-sensor:{d.id}", ControlStatus.ACTIVE,
                        CoverageDimension.SENSOR, 0.85, now, verified_at=d.monitoring_activated_at,
                    ))
                    obs.controls.append(_control(
                        ControlType.MONITORING, f"db-health:{d.id}", ControlStatus.ACTIVE,
                        CoverageDimension.HEALTH, 0.85, now,
                    ))
        add_caps(obs, has_active)
        out.append(obs)
    return out


def _rag_mcp_surfaces(session, org, now, vmax, add_caps):  # type: ignore[no-untyped-def]
    out: list[SurfaceObservation] = []
    rag = session.scalars(
        select(RagConnectorRecord).where(RagConnectorRecord.organization_id == org)
    ).all()
    mcp = session.scalars(
        select(McpConnectorRecord).where(McpConnectorRecord.organization_id == org)
    ).all()
    deployments = session.scalars(
        select(AiTripwireDeploymentRecord).where(
            AiTripwireDeploymentRecord.organization_id == org
        )
    ).all()
    rag_deploys = [d for d in deployments if d.surface_type == "rag_document"]
    mcp_deploys = [d for d in deployments if d.surface_type != "rag_document"]
    for connectors, deploys, stype in (
        (rag, rag_deploys, SurfaceType.RAG), (mcp, mcp_deploys, SurfaceType.MCP)
    ):
        for c in connectors:
            name = str(
                getattr(c, "index_or_collection", None) or getattr(c, "server_reference", "") or ""
            )
            surface = _surface(
                stype, str(c.id), name, sensitivity=_sensitivity_for(name), business=0.7,
                exposure=0.7, attack=0.6, measured=True,
                freshness_hours=_hours_since(c.created_at, now), metadata_completeness=0.7,
            )
            obs = SurfaceObservation(surface)
            has_active = False
            for d in [x for x in deploys if x.connector_id == c.id]:
                status = _decoy_status(d.status, d.expires_at, now)
                eff = scoring.control_effectiveness(
                    status=status, believability=0.7,
                    verified_at=d.monitoring_activated_at, now=now,
                    verification_max_age_hours=vmax,
                )
                obs.controls.append(SurfaceControl(
                    control_type=ControlType.DECOY, control_reference_id=str(d.id)[:128],
                    status=status, effectiveness_score=eff, confidence=0.9,
                    last_verified_at=d.monitoring_activated_at,
                    dimension=CoverageDimension.PLACEMENT,
                ))
                if status == ControlStatus.ACTIVE:
                    has_active = True
                    if d.monitoring_activated_at is not None:
                        obs.controls.append(_control(
                            ControlType.SENSOR, f"ai-sensor:{d.id}", ControlStatus.ACTIVE,
                            CoverageDimension.SENSOR, 0.85, now,
                            verified_at=d.monitoring_activated_at,
                        ))
                        obs.controls.append(_control(
                            ControlType.MONITORING, f"ai-health:{d.id}", ControlStatus.ACTIVE,
                            CoverageDimension.HEALTH, 0.85, now,
                        ))
                    if d.verification_hash is not None:
                        obs.controls.append(_control(
                            ControlType.DECOY, f"ai-verify:{d.id}", ControlStatus.ACTIVE,
                            CoverageDimension.VERIFICATION, 0.85, now,
                            verified_at=d.monitoring_activated_at,
                        ))
            add_caps(obs, has_active)
            out.append(obs)
    return out


def _browser_surfaces(session, org, now, add_caps):  # type: ignore[no-untyped-def]
    import json

    out: list[SurfaceObservation] = []
    policy = session.scalars(
        select(BrowserAiPolicyRecord).where(BrowserAiPolicyRecord.organization_id == org)
    ).first()
    if policy is None:
        return out
    rules = json.loads(policy.rules_data or "[]")
    active_sensor = session.scalars(
        select(func.count()).select_from(BrowserAiPolicyRecord).where(
            BrowserAiPolicyRecord.organization_id == org, BrowserAiPolicyRecord.enabled.is_(True)
        )
    ).one() > 0
    for rule in rules:
        domain = str(rule.get("domain", ""))
        classification = str(rule.get("classification", "unknown"))
        surface = _surface(
            SurfaceType.BROWSER_AI, domain, domain,
            sensitivity=0.7 if classification in ("shadow", "unknown") else 0.4, business=0.6,
            exposure=0.8, attack=0.6, measured=True,
            freshness_hours=_hours_since(policy.updated_at, now), metadata_completeness=0.6,
        )
        obs = SurfaceObservation(surface)
        has_active = policy.enabled and active_sensor
        if has_active:
            obs.controls.append(_control(
                ControlType.SENSOR, f"browser:{domain}", ControlStatus.ACTIVE,
                CoverageDimension.SENSOR, 0.8, now,
            ))
            obs.controls.append(_control(
                ControlType.DECOY, f"browser-policy:{domain}", ControlStatus.ACTIVE,
                CoverageDimension.PLACEMENT, 0.75, now,
            ))
            obs.controls.append(_control(
                ControlType.MONITORING, f"browser-health:{domain}", ControlStatus.ACTIVE,
                CoverageDimension.HEALTH, 0.8, now,
            ))
        add_caps(obs, has_active)
        out.append(obs)
    return out


def _agent_surfaces(session, org, now, add_caps):  # type: ignore[no-untyped-def]
    out: list[SurfaceObservation] = []
    sensors = session.scalars(
        select(AgentSensorRecord).where(AgentSensorRecord.organization_id == org)
    ).all()
    has_policy = session.scalars(
        select(AgentScopePolicyRecord.id).where(
            AgentScopePolicyRecord.organization_id == org
        ).limit(1)
    ).first() is not None
    for s in sensors:
        surface = _surface(
            SurfaceType.AI_AGENT, str(s.id), s.name, sensitivity=0.7, business=0.7, exposure=0.7,
            attack=0.6, measured=True, freshness_hours=_hours_since(s.last_seen_at, now),
            metadata_completeness=0.6,
        )
        obs = SurfaceObservation(surface)
        has_active = s.status == "active"
        if has_active:
            obs.controls.append(_control(
                ControlType.SENSOR, f"agent:{s.id}", ControlStatus.ACTIVE,
                CoverageDimension.SENSOR, 0.8, now, verified_at=s.last_seen_at,
            ))
            obs.controls.append(_control(
                ControlType.MONITORING, f"agent-health:{s.id}", ControlStatus.ACTIVE,
                CoverageDimension.HEALTH, 0.8, now,
            ))
            if has_policy:
                obs.controls.append(_control(
                    ControlType.DECOY, f"agent-scope:{s.id}", ControlStatus.ACTIVE,
                    CoverageDimension.PLACEMENT, 0.75, now,
                ))
                obs.controls.append(_control(
                    ControlType.MONITORING, f"agent-identity:{s.id}", ControlStatus.ACTIVE,
                    CoverageDimension.IDENTITY, 0.8, now,
                ))
        add_caps(obs, has_active)
        out.append(obs)
    return out
