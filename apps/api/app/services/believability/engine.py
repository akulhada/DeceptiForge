"""Explainable evaluator that never mutates generated decoys."""

from dataclasses import dataclass, field

from app.models.domain.decoy import (
    BelievabilityDecision,
    BelievabilitySafetyReport,
    BelievabilityScoreBreakdown,
    DecoyAsset,
)
from app.models.domain.intelligence import (
    OrganizationContextProfile,
    PlacementRecommendation,
    RepositoryIntelligenceProfile,
)
from app.services.believability.collision import CollisionChecker
from app.services.believability.safety import SafetyValidator
from app.services.believability.scoring import DimensionScorer, ScoringWeights, weighted_average


@dataclass(frozen=True)
class BelievabilitySafetyConfig:
    weights: ScoringWeights = field(default_factory=ScoringWeights)
    reserved_names: tuple[str, ...] = ()
    accept_believability: float = 80
    accept_safety: float = 85


class BelievabilitySafetyEngine:
    def __init__(
        self,
        scorer: DimensionScorer | None = None,
        safety: SafetyValidator | None = None,
        collisions: CollisionChecker | None = None,
    ) -> None:
        self._scorer = scorer or DimensionScorer()
        self._safety = safety or SafetyValidator()
        self._collisions = collisions or CollisionChecker()

    def evaluate(
        self,
        asset: DecoyAsset,
        context: OrganizationContextProfile,
        repository: RepositoryIntelligenceProfile,
        placement: PlacementRecommendation,
        config: BelievabilitySafetyConfig | None = None,
    ) -> BelievabilitySafetyReport:
        config = config or BelievabilitySafetyConfig()
        inertness, accidental, trap, failures = self._safety.evaluate(asset)
        collision, collision_notes = self._collisions.risk(
            asset, context, repository, config.reserved_names
        )
        scores = self._scorer.scores(asset, context, placement, inertness)
        believability = weighted_average(
            scores,
            config.weights,
            ("naming", "context", "placement", "schema", "entropy", "business", "traceability"),
        )
        safety = weighted_average(
            {
                **scores,
                "collision": 100 - collision,
                "accidental_use": 100 - accidental,
                "obvious_trap": 100 - trap,
            },
            config.weights,
            ("inertness", "collision", "accidental_use", "obvious_trap"),
        )
        breakdown = BelievabilityScoreBreakdown(
            naming_realism=scores["naming"],
            context_fit=scores["context"],
            placement_compatibility=scores["placement"],
            schema_completeness=scores["schema"],
            entropy_realism=scores["entropy"],
            business_realism=scores["business"],
            traceability_quality=scores["traceability"],
            safety_inertness=inertness,
            production_collision_risk=collision,
            accidental_use_risk=accidental,
            obvious_trap_risk=trap,
        )
        hard_failures = list(failures)
        if not asset.validation.valid:
            hard_failures.append("generated validation is invalid")
        if scores["traceability"] == 0:
            hard_failures.append("traceability metadata is missing")
        if hard_failures or collision >= 80 or safety < 70:
            decision = BelievabilityDecision.REJECT
        elif (
            believability >= config.accept_believability
            and safety >= config.accept_safety
            and collision <= 20
            and trap <= 10
        ):
            decision = BelievabilityDecision.ACCEPT
        else:
            decision = BelievabilityDecision.WARN
        warnings = tuple(note for note in (*collision_notes,) if note) + (
            ("Sparse context limits naming confidence.",) if not context.naming_profile else ()
        )
        fixes = tuple(
            item
            for item in (
                "Use a non-colliding name." if collision >= 20 else "",
                (
                    "Restore a trace identifier in payload and trigger metadata."
                    if scores["traceability"] == 0
                    else ""
                ),
                (
                    "Replace visible deception markers with context-native terminology."
                    if trap
                    else ""
                ),
                (
                    "Use the approved inert secret format and demo-safe metadata."
                    if inertness < 100
                    else ""
                ),
                (
                    "Align the asset with its accepted placement template."
                    if scores["placement"] == 0
                    else ""
                ),
            )
            if item
        )
        return BelievabilitySafetyReport(
            decoy_id=asset.decoy_id,
            overall_believability_score=believability,
            overall_safety_score=safety,
            decision=decision,
            breakdown=breakdown,
            explainability_notes=(
                f"Believability is {believability:.1f}/100; safety is {safety:.1f}/100.",
                "Scores use deterministic template, context, and collision evidence.",
            ),
            failed_checks=tuple(hard_failures),
            warnings=warnings,
            recommended_fixes=fixes,
        )
