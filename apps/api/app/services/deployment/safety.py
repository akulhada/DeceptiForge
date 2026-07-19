# Purpose: decide which decoy assets may be safely deployed, and why.
# Responsibilities: require an accepted validation report per asset, enforce the path policy, check
#   no production-name collision, and confirm the decoy is inert (no real credentials/customer data,
#   no auth capability). Pure and deterministic; re-run immediately before any write.
from __future__ import annotations

from dataclasses import dataclass, field

from app.models.domain.decoy import (
    BelievabilityDecision,
    BelievabilitySafetyReport,
    DecoyAsset,
    DecoyGenerationPlan,
)
from app.services.deployment.policy import PathPolicy


@dataclass(frozen=True)
class AssetSafety:
    asset: DecoyAsset
    deployable: bool
    reasons: tuple[str, ...]


@dataclass
class SafetyEvaluation:
    deployable_assets: list[DecoyAsset] = field(default_factory=list)
    rejected: list[AssetSafety] = field(default_factory=list)
    collision_ok: bool = True

    @property
    def any_deployable(self) -> bool:
        return bool(self.deployable_assets)


def _is_inert(asset: DecoyAsset) -> bool:
    meta = asset.safety_metadata
    return (
        meta.contains_real_credentials is False
        and meta.contains_real_customer_data is False
        and meta.authentication_capability == "none"
    )


def evaluate(
    plan: DecoyGenerationPlan,
    reports: tuple[BelievabilitySafetyReport, ...],
    policy: PathPolicy,
) -> SafetyEvaluation:
    """Return which of the plan's assets are safe to deploy under the given policy."""
    decision_by_decoy = {report.decoy_id: report.decision for report in reports}
    result = SafetyEvaluation()
    for asset in plan.assets:
        reasons: list[str] = []
        if decision_by_decoy.get(asset.decoy_id) is not BelievabilityDecision.ACCEPT:
            reasons.append("no accepted validation report")
        try:
            policy.check_path(asset.target_location)
        except Exception as error:  # noqa: BLE001 - message is safe policy text
            reasons.append(str(error))
        if asset.collision_check.collision_detected:
            reasons.append("production-name collision detected")
            result.collision_ok = False
        if not _is_inert(asset):
            reasons.append("decoy is not inert")
        if not asset.trigger_metadata.trace_identifier:
            reasons.append("missing trace identifier")
        if reasons:
            result.rejected.append(AssetSafety(asset, False, tuple(reasons)))
        else:
            result.deployable_assets.append(asset)
    return result
