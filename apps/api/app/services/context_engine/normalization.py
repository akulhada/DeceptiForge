"""Normalize scanner evidence without changing its source semantics."""
from app.models.domain.intelligence import NamingCategory
from app.services.context_engine.features import ContextFeatures


class NormalizedContext:
    def __init__(self, features: ContextFeatures) -> None:
        self.features = features
        profile = features.profile
        self.vocabulary = profile.naming_profile.vocabulary if profile.naming_profile else ()
        self.environment_conventions = tuple(
            f"{item.category.value}:{item.style.value}:{item.separator.value}"
            for item in (profile.naming_profile.naming_style if profile.naming_profile else ())
            if item.category is NamingCategory.ENVIRONMENT_VARIABLE
        )
        self.technologies = features.technologies


class ContextNormalizer:
    def normalize(self, features: ContextFeatures) -> NormalizedContext:
        return NormalizedContext(features)
