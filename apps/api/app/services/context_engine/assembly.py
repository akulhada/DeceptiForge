"""Assemble the public immutable context profile from prior deterministic layers."""

from app.models.domain.intelligence import ContextReasoning, OrganizationContextProfile
from app.services.context_engine.classification import ContextClassification
from app.services.context_engine.normalization import NormalizedContext
from app.services.context_engine.scoring import ContextScores


class ContextProfileAssembler:
    def assemble(
        self,
        context: NormalizedContext,
        classification: ContextClassification,
        scores: ContextScores,
    ) -> OrganizationContextProfile:
        profile = context.features.profile
        high_value = tuple(zone.name for zone in scores.zones if zone.priority >= 0.8)
        workflows = tuple(
            name
            for name, present in (
                ("ci_cd", bool(profile.cicd)),
                ("cloud", bool(profile.cloud_providers)),
                ("database", bool(profile.databases)),
                ("documentation", bool(profile.documentation)),
                ("mcp", bool(profile.mcp_configurations)),
                ("package_management", bool(profile.package_managers)),
            )
            if present
        )
        return OrganizationContextProfile(
            repository_name=profile.repository_name,
            organization_archetype=classification.archetype,
            stack_maturity=classification.maturity,
            primary_technical_vocabulary=context.vocabulary,
            environment_naming_conventions=context.environment_conventions,
            likely_sensitive_asset_types=scores.sensitive_assets,
            likely_decoy_placement_zones=scores.zones,
            high_value_systems=high_value,
            likely_workflow_surfaces=workflows,
            ai_exposure_risk=scores.ai_risk,
            database_sensitivity_confidence=scores.database_confidence,
            documentation_culture=classification.documentation,
            operational_complexity=(
                "high"
                if len(profile.services) >= 3 or bool(profile.infrastructure.kubernetes_files)
                else (
                    "moderate"
                    if profile.services or profile.infrastructure.docker_files
                    else "low" if context.features.evidence_count else "unknown"
                )
            ),
            security_posture_hints=tuple(item.category for item in profile.risk_areas),
            technologies=(*profile.languages, *profile.frameworks, *profile.technologies),
            naming_profile=profile.naming_profile,
            confidence_metadata=scores.metadata,
            reasoning=(
                ContextReasoning(
                    dimension="organization_archetype",
                    conclusion=classification.archetype.value,
                    evidence=tuple(sorted(context.technologies))[:10],
                ),
            ),
            confidence=scores.confidence,
        )
