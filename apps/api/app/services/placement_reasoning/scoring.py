"""Fixed, explainable scoring for placement candidates."""

from app.models.domain.intelligence import (
    OrganizationContextProfile,
    PlacementCandidate,
    PlacementScore,
)


class PlacementScorer:
    def score(
        self, candidate: PlacementCandidate, context: OrganizationContextProfile
    ) -> PlacementScore:
        signals = candidate.signals
        # Detection quality weights visibility and interaction surfaces that create evidence.
        detection_quality = (
            0.30 * signals.attacker_visibility
            + 0.20 * signals.ai_agent_access
            + 0.15 * signals.insider_access
            + 0.15 * signals.exportability
            + 0.10 * signals.accidental_exposure
            + 0.10 * signals.plausibility
        )
        visibility = max(signals.attacker_visibility, signals.ai_agent_access)
        priority = (
            0.40 * detection_quality
            + 0.25 * visibility
            + 0.20 * signals.context_alignment
            + 0.15 * signals.safety
        )
        evidence_factor = 0.5 + min(0.5, len(candidate.evidence) / 6)
        confidence = (
            (signals.safety + signals.context_alignment + context.confidence) / 3 * evidence_factor
        )
        return PlacementScore(
            priority=round(priority, 3),
            confidence=round(confidence, 3),
            detection_quality=round(detection_quality, 3),
            risk=round(1 - signals.safety, 3),
            expected_visibility=round(visibility, 3),
            false_positive_risk=signals.false_positive_risk,
        )
