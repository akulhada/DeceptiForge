"""Safety gates that keep recommendations away from live production behavior."""

from app.models.domain.intelligence import (
    PlacementCandidate,
    PlacementScore,
    PlacementTargetType,
)


class PlacementSafetyFilter:
    minimum_safety = 0.65
    maximum_false_positive_risk = 0.45

    def rejection_reasons(
        self, candidate: PlacementCandidate, score: PlacementScore
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if candidate.target_type is PlacementTargetType.ENVIRONMENT_FILE:
            reasons.append("production environment files can break application behavior")
        if candidate.requires_nonproduction_scope:
            reasons.append("database placement requires an explicit non-production scope")
        if candidate.signals.safety < self.minimum_safety:
            reasons.append("location safety is below the required threshold")
        if score.false_positive_risk > self.maximum_false_positive_risk:
            reasons.append("expected false-positive risk is above the allowed threshold")
        return tuple(reasons)
