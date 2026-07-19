# Purpose: build the compact, organization-scoped trace registry delivered to browser sensors.
# Responsibilities: collect active trace identifiers from the deployment tripwire surfaces
#   (repository, database honey, RAG/MCP) and emit only an irreversible match token per trace —
#   never a full decoy document, real secret, or marker plaintext. Bounded in size and expiry-aware.
# Dependencies: records, browser domain, settings, session.
from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.models.domain.browser_sensor import (
    TraceMatchMode,
    TraceRegistryDoc,
    TraceRegistryEntry,
)
from app.models.records import (
    AiTripwireDeploymentRecord,
    BrowserAiPolicyRecord,
    DatabaseHoneyRecordRecord,
    DeploymentTripwireRecord,
)


def fingerprint(trace_id: str, mode: TraceMatchMode) -> str:
    """Irreversible lookup token for a trace marker. Normalized mode lowercases and strips so the
    extension can match case/space variants without ever shipping the raw marker."""
    value = trace_id.strip()
    if mode == TraceMatchMode.NORMALIZED:
        value = value.lower()
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_registry(session: Session, organization_id, settings: Settings) -> TraceRegistryDoc:  # type: ignore[no-untyped-def]
    policy = session.scalars(
        select(BrowserAiPolicyRecord).where(
            BrowserAiPolicyRecord.organization_id == organization_id
        )
    ).first()
    policy_version = policy.policy_version if policy else 0
    mode = TraceMatchMode(policy.trace_match_mode) if policy else TraceMatchMode.EXACT
    limit = settings.browser_sensor_max_registry_entries

    seen: dict[str, TraceRegistryEntry] = {}

    def add(trace_id: str, category: str, expires_at: datetime | None) -> None:
        if not trace_id or trace_id in seen or len(seen) >= limit:
            return
        seen[trace_id] = TraceRegistryEntry(
            trace_id=trace_id,
            match_token=fingerprint(trace_id, mode),
            match_mode=mode,
            decoy_category=category,
            status="active",
            expires_at=expires_at,
        )

    for ai in session.scalars(
        select(AiTripwireDeploymentRecord).where(
            AiTripwireDeploymentRecord.organization_id == organization_id,
            AiTripwireDeploymentRecord.status == "deployed",
        )
    ).all():
        add(ai.trace_id, ai.surface_type, ai.expires_at)

    for repo_tw in session.scalars(
        select(DeploymentTripwireRecord).where(
            DeploymentTripwireRecord.organization_id == organization_id,
            DeploymentTripwireRecord.status == "active",
        )
    ).all():
        add(repo_tw.trace_identifier, "repository", None)

    for honey in session.scalars(
        select(DatabaseHoneyRecordRecord).where(
            DatabaseHoneyRecordRecord.organization_id == organization_id,
            DatabaseHoneyRecordRecord.status == "active",
        )
    ).all():
        add(honey.trace_id, "database_record", None)

    return TraceRegistryDoc(
        organization_id=str(organization_id),
        policy_version=policy_version,
        entries=tuple(seen.values()),
        generated_at=datetime.now(UTC),
    )
