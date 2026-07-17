"""Bounded name collision scoring against scanner and naming evidence."""

from difflib import SequenceMatcher

from app.models.domain.decoy import (
    DecoyAsset,
    GeneratedDatabaseRecord,
    GeneratedDocument,
    GeneratedSecret,
)
from app.models.domain.intelligence import OrganizationContextProfile, RepositoryIntelligenceProfile


class CollisionChecker:
    def risk(
        self,
        asset: DecoyAsset,
        context: OrganizationContextProfile,
        repository: RepositoryIntelligenceProfile,
        reserved_names: tuple[str, ...],
    ) -> tuple[float, tuple[str, ...]]:
        candidate = self._name(asset).lower()
        corpus = self._corpus(context, repository, reserved_names)
        if not corpus:
            return 0.0, ()
        similarity = max(SequenceMatcher(None, candidate, item).ratio() for item in corpus)
        exact = candidate in corpus
        risk = 100.0 if exact else round(similarity * 80, 1) if similarity >= 0.8 else 0.0
        notes = (
            (f"Exact collision with observed name: {candidate}.",)
            if exact
            else (
                (f"Closest observed-name similarity is {similarity:.2f}.",)
                if similarity >= 0.8
                else ()
            )
        )
        return risk, notes

    @staticmethod
    def _name(asset: DecoyAsset) -> str:
        if isinstance(asset.payload, GeneratedSecret):
            return asset.payload.key_name
        if isinstance(asset.payload, GeneratedDocument):
            return asset.payload.title
        if isinstance(asset.payload, GeneratedDatabaseRecord):
            return asset.payload.table_name
        return ""

    @staticmethod
    def _corpus(
        context: OrganizationContextProfile,
        repository: RepositoryIntelligenceProfile,
        reserved_names: tuple[str, ...],
    ) -> set[str]:
        naming = context.naming_profile
        samples = (
            ()
            if naming is None
            else tuple(
                sample for convention in naming.naming_style for sample in convention.samples
            )
        )
        services = tuple(item.name for item in repository.services)
        databases = tuple(item.name for item in repository.databases)
        secret_patterns = tuple(
            pattern for location in repository.secret_locations for pattern in location.patterns
        )
        return {
            item.lower()
            for item in (*samples, *services, *databases, *secret_patterns, *reserved_names)
        }
