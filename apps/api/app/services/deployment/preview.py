# Purpose: generate the exact, deterministic deployment preview (change set) before any write.
# Responsibilities: render inert decoy files for the deployable assets, build unified diffs and
#   content hashes, enforce file/byte ceilings, summarize blast radius, and compute a stable
#   preview hash used for drift/stale detection. No repository or network access here.
# Dependencies: deployment domain models, policy, safety, rendering.
from __future__ import annotations

import difflib
import hashlib
from datetime import datetime
from uuid import UUID

from app.models.domain.decoy import BelievabilitySafetyReport, DecoyGenerationPlan
from app.models.domain.deployment import (
    ChangeSetItem,
    DeploymentOperation,
    DeploymentPreview,
)
from app.services.deployment.policy import PathPolicy
from app.services.deployment.rendering import content_sha256, render_decoy_content
from app.services.deployment.safety import SafetyEvaluation, evaluate


class PreviewError(Exception):
    """Raised when a safe preview cannot be produced (no deployable assets, or over limits)."""


def _unified_diff_for_create(path: str, content: str) -> str:
    diff = difflib.unified_diff(
        [], content.splitlines(keepends=True), fromfile="/dev/null", tofile=f"b/{path}"
    )
    return "".join(diff)


def build_preview(
    *,
    deployment_id: UUID,
    repository_id: UUID,
    base_branch: str,
    base_commit_sha: str,
    target_branch: str,
    plan: DecoyGenerationPlan,
    reports: tuple[BelievabilitySafetyReport, ...],
    policy: PathPolicy,
    expires_at: datetime | None,
) -> tuple[DeploymentPreview, dict[UUID, str]]:
    """Return the preview and a map of decoy_id -> rendered content for the deployable assets."""
    safety: SafetyEvaluation = evaluate(plan, reports, policy)
    if not safety.any_deployable:
        raise PreviewError("no assets passed safety and path policy; nothing to deploy")

    items: list[ChangeSetItem] = []
    contents: dict[UUID, str] = {}
    total_bytes = 0
    for asset in safety.deployable_assets:
        content = render_decoy_content(asset)
        contents[asset.decoy_id] = content
        total_bytes += len(content.encode("utf-8"))
        items.append(
            ChangeSetItem(
                decoy_id=asset.decoy_id,
                decoy_type=asset.decoy_type.value,
                target_path=asset.target_location,
                operation=DeploymentOperation.CREATE,
                trace_identifier=asset.trigger_metadata.trace_identifier,
                original_content_hash=None,
                proposed_content_hash=content_sha256(content),
                unified_diff=_unified_diff_for_create(asset.target_location, content),
                warnings=(),
            )
        )

    policy.check_totals(len(items), total_bytes)

    warnings = tuple(
        f"{rejected.asset.target_location}: {'; '.join(rejected.reasons)}"
        for rejected in safety.rejected
    )
    decoy_types = tuple(sorted({item.decoy_type for item in items}))
    traces = tuple(sorted({item.trace_identifier for item in items}))
    preview_hash = _preview_hash(base_commit_sha, target_branch, items)
    preview = DeploymentPreview(
        deployment_id=deployment_id,
        repository_id=repository_id,
        target_branch=target_branch,
        base_branch=base_branch,
        base_commit_sha=base_commit_sha,
        items=tuple(items),
        decoy_types=decoy_types,
        trace_identifiers=traces,
        validation_decision="accept",
        collision_ok=safety.collision_ok,
        expected_monitoring_registration=traces,
        expires_at=expires_at,
        rollback_strategy=(
            "Revert only deployment-owned content (matched by deployment marker + content hash) "
            "through a rollback branch and pull request. The default branch is never rewritten."
        ),
        warnings=warnings,
        changed_files=len(items),
        changed_bytes=total_bytes,
        blast_radius=_blast_radius(items, total_bytes),
        preview_hash=preview_hash,
    )
    return preview, contents


def _preview_hash(base_commit_sha: str, target_branch: str, items: list[ChangeSetItem]) -> str:
    canonical = "\n".join(
        [base_commit_sha, target_branch]
        + [f"{i.target_path}:{i.operation.value}:{i.proposed_content_hash}" for i in items]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _blast_radius(items: list[ChangeSetItem], total_bytes: int) -> str:
    prefixes = sorted({item.target_path.split("/", 1)[0] for item in items})
    return (
        f"low: {len(items)} new inert file(s) totaling {total_bytes} bytes under "
        f"{', '.join(prefixes)}; no existing files modified or deleted"
    )
