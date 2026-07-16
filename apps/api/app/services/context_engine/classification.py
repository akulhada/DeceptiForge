"""Rule-based organization and operational classification."""
from app.models.domain.intelligence import (
    DocumentationCulture,
    OrganizationArchetype,
    StackMaturity,
)
from app.services.context_engine.normalization import NormalizedContext


class ContextClassification:
    def __init__(self, context: NormalizedContext) -> None:
        profile, technologies = context.features.profile, context.technologies
        cloud = bool(
            profile.cloud_providers
            or profile.infrastructure.terraform_files
            or profile.infrastructure.kubernetes_files
        )
        data = bool(profile.databases)
        developer = any(
            value in technologies for value in {"typescript", "python", "node.js"}
        ) and bool(profile.package_managers)
        self.archetype = (
            OrganizationArchetype.CLOUD_NATIVE_PLATFORM
            if cloud
            else OrganizationArchetype.DATA_SERVICE
            if data
            else OrganizationArchetype.DEVELOPER_TOOLING
            if developer
            else OrganizationArchetype.APPLICATION_SERVICE
            if technologies
            else OrganizationArchetype.UNKNOWN
        )
        signals = sum(
            bool(value)
            for value in (
                profile.frameworks,
                profile.package_managers,
                profile.services,
                profile.cicd,
                profile.infrastructure.docker_files,
                profile.infrastructure.terraform_files,
            )
        )
        self.maturity = (
            StackMaturity.MATURE
            if signals >= 5
            else StackMaturity.ESTABLISHED
            if signals >= 3
            else StackMaturity.EXPERIMENTAL
            if signals
            else StackMaturity.UNKNOWN
        )
        docs = len(profile.documentation)
        self.documentation = (
            DocumentationCulture.STRUCTURED
            if docs >= 3
            else DocumentationCulture.OPERATIONAL
            if docs >= 2
            else DocumentationCulture.LIGHT
            if docs
            else DocumentationCulture.NONE
        )


class ContextClassifier:
    def classify(self, context: NormalizedContext) -> ContextClassification:
        return ContextClassification(context)
