# Purpose: build normalized, minimized feature snapshots for the learning boundary.
# Responsibilities: translate an already-normalized analysis result into the versioned
#   NormalizedFeatures contract (categories, buckets, 0..1 scores only), enforce a hard minimization
#   guard that REJECTS anything resembling raw content/paths/secrets, and derive stable hashes for
#   deduplication. Never accepts or stores source files, credentials, customer records, prompts, or
#   model output. Dependencies: learning domain contracts. No I/O.
from __future__ import annotations

import hashlib
import json
import re

from app.models.domain.analysis_preview import AnalysisPreviewResponse
from app.models.domain.learning import (
    FEATURE_SCHEMA_VERSION,
    Bucket,
    NormalizedFeatures,
    bucket_of,
)


class MinimizationError(ValueError):
    """Raised when a candidate feature payload contains content that must never be learned from."""


# Shapes that indicate raw content rather than a category: path separators, file extensions,
# secret-ish tokens, URLs, and long opaque strings.
_FORBIDDEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"[/\\]"),  # path separator
    re.compile(r"\.[A-Za-z0-9]{1,5}$"),  # file extension
    re.compile(r"://"),  # URL
    re.compile(r"(?i)\b(secret|token|password|api[_-]?key|bearer|private[_-]?key)\b"),
    # SCREAMING_SNAKE tokens are environment-variable names, i.e. raw configuration, not categories.
    # Legitimate categories are lowercase (see _category), so this cannot reject e.g.
    # "secrets_and_credentials".
    re.compile(r"^[A-Z][A-Z0-9_]{2,}$"),
    re.compile(r"^[A-Za-z0-9+/=]{40,}$"),  # base64-ish blob
    re.compile(r"(?i)-----BEGIN"),  # PEM material
)
_MAX_CATEGORY_LEN = 64


def _assert_category(value: str, field: str) -> str:
    """A category must be a short, non-identifying token — never a path, secret, or blob."""
    if len(value) > _MAX_CATEGORY_LEN:
        raise MinimizationError(f"{field}: category exceeds {_MAX_CATEGORY_LEN} characters")
    for pattern in _FORBIDDEN_PATTERNS:
        if pattern.search(value):
            raise MinimizationError(f"{field}: value looks like raw content, not a category")
    return value


def assert_minimized(features: NormalizedFeatures) -> NormalizedFeatures:
    """Guard every string in the snapshot. Cheap, total, and verifiable by reading this function."""
    _assert_category(features.dominant_language_category, "dominant_language_category")
    _assert_category(features.repository_architecture, "repository_architecture")
    _assert_category(features.business_domain_category, "business_domain_category")
    for value in features.framework_categories:
        _assert_category(value, "framework_categories")
    for value in features.sensitive_zone_categories:
        _assert_category(value, "sensitive_zone_categories")
    return features


def _category(value: str) -> str:
    """Collapse a free-form label to a safe lowercase category token."""
    token = re.sub(r"[^a-z0-9_]+", "_", value.strip().lower()).strip("_")
    return token[:_MAX_CATEGORY_LEN] or "unknown"


def features_from_preview(result: AnalysisPreviewResponse) -> NormalizedFeatures:
    """Derive normalized features from a deterministic analysis result.

    The input is already minimized (the preview contract holds no raw content), and everything
    carried across is a category, bucket, or score.
    """
    summary = result.input_summary
    profile = result.context_profile
    features = NormalizedFeatures(
        dominant_language_category=_category(profile.dominant_technical_stack.value.split(",")[0]),
        framework_categories=tuple(
            sorted({_category(v) for v in profile.dominant_technical_stack.value.split(",")[1:]})
        )[:20],
        repository_architecture=_category(profile.service_architecture.value),
        business_domain_category=_category(profile.probable_business_domain.value),
        service_count_bucket=bucket_of(summary.service_count),
        documentation_density_bucket=bucket_of(summary.documentation_signal_count),
        ai_surface_count_bucket=bucket_of(summary.ai_surface_count),
        deployment_complexity_bucket=bucket_of(summary.framework_count + summary.database_count),
        sensitive_zone_categories=tuple(
            sorted({_category(z.category) for z in result.sensitive_zones})
        )[:20],
        secrets_exposure_score=min(1.0, round(summary.secret_location_count / 10, 4)),
        naming_consistency_score=round(result.vocabulary.confidence, 4),
        profile_confidence=round(result.confidence.overall, 4),
        signal_conflict_score=round(result.confidence.conflict, 4),
    )
    return assert_minimized(features)


def feature_hash(features: NormalizedFeatures, schema_version: str = FEATURE_SCHEMA_VERSION) -> str:
    """Stable content hash for deduplication. Same features -> same snapshot row."""
    payload = json.dumps(
        {"schema": schema_version, "features": features.model_dump(mode="json")},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def source_id_hash(organization_id: str, source_identifier: str) -> str:
    """Hash a source reference so no repository name or path is ever persisted.

    Salted per organization so the same identifier in two tenants does not produce a linkable hash.
    """
    return hashlib.sha256(f"{organization_id}:{source_identifier}".encode()).hexdigest()


__all__ = [
    "Bucket",
    "MinimizationError",
    "assert_minimized",
    "feature_hash",
    "features_from_preview",
    "source_id_hash",
]
