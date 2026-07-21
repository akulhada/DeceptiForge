"""Controlled learning and calibration.

Learns only from normalized features and explicit outcomes — never source content, secrets,
customer records, prompts, or model output. Calibration runs offline, produces CANDIDATE weights
only, and can never activate itself or alter deterministic safety rules.
"""

from app.services.learning.calibration import OutcomeObservation, attribute, build_candidate
from app.services.learning.features import (
    MinimizationError,
    assert_minimized,
    feature_hash,
    features_from_preview,
)
from app.services.learning.versions import VersionTransitionError, VersionView

__all__ = [
    "MinimizationError",
    "OutcomeObservation",
    "VersionTransitionError",
    "VersionView",
    "assert_minimized",
    "attribute",
    "build_candidate",
    "feature_hash",
    "features_from_preview",
]
