"""Plans validated decoy assets from accepted placement recommendations only."""

from uuid import NAMESPACE_URL, UUID, uuid5

from app.models.domain.decoy import (
    BelievabilityInputs,
    DecoyAsset,
    DecoyGenerationPlan,
    RejectedGenerationCandidate,
    RotationMetadata,
    TriggerMetadataPlaceholder,
)
from app.models.domain.intelligence import (
    OrganizationContextProfile,
    PlacementPlan,
    RepositoryIntelligenceProfile,
)
from app.services.decoy_generation.generators import PayloadGenerators
from app.services.decoy_generation.templates import DecoyTemplateRegistry
from app.services.decoy_generation.validation import DecoyValidationPipeline


class DecoyGenerationConfig:
    def __init__(
        self, namespace: str = "deceptiforge", reserved_names: tuple[str, ...] = ()
    ) -> None:
        self.namespace = namespace
        self.reserved_names = reserved_names


class DecoyGenerationPlanner:
    def __init__(
        self,
        registry: DecoyTemplateRegistry | None = None,
        generators: PayloadGenerators | None = None,
        validator: DecoyValidationPipeline | None = None,
    ) -> None:
        self._registry = registry or DecoyTemplateRegistry()
        self._generators = generators or PayloadGenerators()
        self._validator = validator or DecoyValidationPipeline()

    def generate(
        self,
        repository: RepositoryIntelligenceProfile,
        context: OrganizationContextProfile,
        placements: PlacementPlan,
        config: DecoyGenerationConfig | None = None,
    ) -> DecoyGenerationPlan:
        config = config or DecoyGenerationConfig()
        assets: list[DecoyAsset] = []
        rejected: list[RejectedGenerationCandidate] = []
        for recommendation in placements.recommendations:
            if (
                recommendation.confidence < 0.65
                or recommendation.expected_false_positive_risk > 0.45
            ):
                rejected.append(
                    RejectedGenerationCandidate(
                        target_location=recommendation.target_location,
                        reasons=("placement fails generator safety admission",),
                    )
                )
                continue
            template = self._registry.select(
                recommendation.future_asset_type_recommendation, recommendation.target_type
            )
            if template is None:
                rejected.append(
                    RejectedGenerationCandidate(
                        target_location=recommendation.target_location,
                        reasons=("no approved template supports this accepted placement",),
                    )
                )
                continue
            placement_id = self._identifier(
                config.namespace,
                repository.repository_name,
                recommendation.target_location,
                "placement",
            )
            decoy_id = self._identifier(
                config.namespace,
                repository.repository_name,
                recommendation.target_location,
                template.template_id.value,
            )
            trace = f"DFG-{decoy_id.hex[:16].upper()}"
            payload = self._generators.generate(recommendation, context, trace)
            validation, collision = self._validator.validate(
                payload, recommendation, template, context, config.reserved_names
            )
            if not validation.valid:
                rejected.append(
                    RejectedGenerationCandidate(
                        target_location=recommendation.target_location, reasons=validation.reasons
                    )
                )
                continue
            assets.append(
                DecoyAsset(
                    decoy_id=decoy_id,
                    decoy_type=template.decoy_kind,
                    target_placement_id=placement_id,
                    target_location=recommendation.target_location,
                    payload=payload,
                    template_id=template.template_id,
                    believability_inputs=BelievabilityInputs(
                        naming_match=0.9,
                        entropy_profile=0.9 if template.decoy_kind.value == "secret" else 0.7,
                        context_match=recommendation.confidence,
                        placement_match=recommendation.placement_priority,
                        schema_realism=1.0,
                        business_realism=0.8,
                        safety_risk=recommendation.risk_score,
                    ),
                    safety_metadata=self._validator.safety_metadata(),
                    collision_check=collision,
                    trigger_metadata=TriggerMetadataPlaceholder(trace_identifier=trace),
                    rotation_metadata=RotationMetadata(
                        rotation_recommendation=(
                            "Rotate on access or every 90 days; no live credential exists."
                        )
                    ),
                    explanation=(
                        (
                            f"Selected {template.template_id.value} for the accepted "
                            f"{recommendation.target_type.value} placement."
                        ),
                        (
                            "Payload is deterministic, inert, and validated against the "
                            "organization context."
                        ),
                    ),
                    validation=validation,
                )
            )
        return DecoyGenerationPlan(
            repository_name=repository.repository_name,
            assets=tuple(assets),
            rejected_candidates=tuple(rejected),
        )

    @staticmethod
    def _identifier(namespace: str, repository_name: str, location: str, purpose: str) -> UUID:
        return uuid5(NAMESPACE_URL, f"{namespace}:{repository_name}:{location}:{purpose}")
