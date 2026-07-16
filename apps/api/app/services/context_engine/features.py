"""Extract only stable, scanner-supplied evidence for context classification."""
from app.models.domain.intelligence import RepositoryIntelligenceProfile


class ContextFeatures:
    def __init__(self, profile: RepositoryIntelligenceProfile) -> None:
        self.profile = profile
        self.technologies = tuple(
            {
                item.name.lower()
                for item in (*profile.languages, *profile.frameworks, *profile.technologies)
            }
        )
        self.evidence_count = sum(
            len(items)
            for items in (
                profile.languages,
                profile.frameworks,
                profile.services,
                profile.databases,
                profile.cloud_providers,
                profile.documentation,
                profile.mcp_configurations,
            )
        )


class ContextFeatureExtractor:
    def extract(self, profile: RepositoryIntelligenceProfile) -> ContextFeatures:
        return ContextFeatures(profile)
