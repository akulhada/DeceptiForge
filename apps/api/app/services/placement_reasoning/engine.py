"""Orchestrates discovery, fixed scoring, safety filtering, and stable ranking."""

from app.models.domain.intelligence import (
    OrganizationContextProfile,
    PlacementPlan,
    PlacementRecommendation,
    RejectedPlacementCandidate,
    RepositoryIntelligenceProfile,
)
from app.services.placement_reasoning.discovery import CandidateDiscovery
from app.services.placement_reasoning.safety import PlacementSafetyFilter
from app.services.placement_reasoning.scoring import PlacementScorer


class PlacementReasoningEngine:
    def __init__(
        self,
        discovery: CandidateDiscovery | None = None,
        scorer: PlacementScorer | None = None,
        safety_filter: PlacementSafetyFilter | None = None,
    ) -> None:
        self._discovery = discovery or CandidateDiscovery()
        self._scorer = scorer or PlacementScorer()
        self._safety_filter = safety_filter or PlacementSafetyFilter()

    def plan(
        self, repository: RepositoryIntelligenceProfile, context: OrganizationContextProfile
    ) -> PlacementPlan:
        accepted = []
        rejected = []
        for candidate in self._discovery.discover(repository, context):
            score = self._scorer.score(candidate, context)
            reasons = self._safety_filter.rejection_reasons(candidate, score)
            if reasons:
                rejected.append(
                    RejectedPlacementCandidate(
                        target_type=candidate.target_type,
                        target_location=candidate.target_location,
                        rejection_reasons=reasons,
                    )
                )
            else:
                accepted.append((candidate, score))
        accepted.sort(
            key=lambda item: (-item[1].priority, -item[1].confidence, item[0].target_location)
        )
        return PlacementPlan(
            repository_name=repository.repository_name,
            context=context,
            recommendations=tuple(
                PlacementRecommendation(
                    target_type=candidate.target_type,
                    target_location=candidate.target_location,
                    placement_priority=score.priority,
                    confidence=score.confidence,
                    reasoning=(
                        f"Evidence-backed location: {candidate.target_location}.",
                        f"Context alignment is {candidate.signals.context_alignment:.2f}.",
                        (
                            f"Safety is {candidate.signals.safety:.2f}; false-positive risk is "
                            f"{score.false_positive_risk:.2f}."
                        ),
                        (
                            f"Detection quality is {score.detection_quality:.2f} from visibility "
                            "and access signals."
                        ),
                    ),
                    expected_detection_quality=score.detection_quality,
                    risk_score=score.risk,
                    expected_attacker_agent_visibility=score.expected_visibility,
                    expected_false_positive_risk=score.false_positive_risk,
                    future_asset_type_recommendation=candidate.future_asset_type,
                    evidence=candidate.evidence,
                )
                for candidate, score in accepted
            ),
            rejected_candidates=tuple(rejected),
        )
