"""Configurable normalized scoring for believability and safety reports."""

from dataclasses import dataclass

from app.models.domain.decoy import (
    DecoyAsset,
    GeneratedDatabaseRecord,
    GeneratedDocument,
    GeneratedSecret,
)
from app.models.domain.intelligence import OrganizationContextProfile, PlacementRecommendation
from app.services.decoy_generation.templates import DecoyTemplateRegistry


@dataclass(frozen=True)
class ScoringWeights:
    naming: float = 15
    context: float = 15
    placement: float = 15
    schema: float = 10
    entropy: float = 10
    business: float = 10
    traceability: float = 10
    inertness: float = 50
    collision: float = 25
    accidental_use: float = 15
    obvious_trap: float = 10


class DimensionScorer:
    def __init__(self, templates: DecoyTemplateRegistry | None = None) -> None:
        self._templates = templates or DecoyTemplateRegistry()

    def scores(
        self,
        asset: DecoyAsset,
        context: OrganizationContextProfile,
        placement: PlacementRecommendation,
        inertness: float,
    ) -> dict[str, float]:
        inputs = asset.believability_inputs
        template = self._templates.select(asset.decoy_type, placement.target_type)
        compatible = template is not None and asset.target_location == placement.target_location
        naming = inputs.naming_match * 100
        if isinstance(asset.payload, GeneratedSecret) and context.environment_naming_conventions:
            naming = (
                100.0
                if asset.payload.key_name.isupper() and "_" in asset.payload.key_name
                else 40.0
            )
        traceability = 100.0 if self._trace_matches(asset) else 0.0
        return {
            "naming": round(naming, 1),
            "context": round(inputs.context_match * 100, 1),
            "placement": 100.0 if compatible else 0.0,
            "schema": 100.0 if asset.validation.valid and template is not None else 0.0,
            "entropy": round(inputs.entropy_profile * 100, 1),
            "business": round(inputs.business_realism * 100, 1),
            "traceability": traceability,
            "inertness": inertness,
        }

    @staticmethod
    def _trace_matches(asset: DecoyAsset) -> bool:
        trace = asset.trigger_metadata.trace_identifier
        if not trace:
            return False
        if isinstance(asset.payload, GeneratedSecret):
            return asset.payload.fake_value.startswith("dfg_inert_")
        if isinstance(asset.payload, (GeneratedDocument, GeneratedDatabaseRecord)):
            return asset.payload.trace_identifier == trace
        return False


def weighted_average(
    values: dict[str, float], weights: ScoringWeights, names: tuple[str, ...]
) -> float:
    configured = {
        "naming": weights.naming,
        "context": weights.context,
        "placement": weights.placement,
        "schema": weights.schema,
        "entropy": weights.entropy,
        "business": weights.business,
        "traceability": weights.traceability,
        "inertness": weights.inertness,
        "collision": weights.collision,
        "accidental_use": weights.accidental_use,
        "obvious_trap": weights.obvious_trap,
    }
    total = sum(configured[name] for name in names)
    return round(sum(values[name] * configured[name] for name in names) / total, 1)
