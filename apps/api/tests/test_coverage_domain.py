# Purpose: verify coverage domain enums, methodology version, and model bounds.
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.domain.coverage import (
    METHODOLOGY_VERSION,
    CoverageDimension,
    InventorySurface,
    SurfaceType,
)


def test_methodology_version_stable() -> None:
    assert METHODOLOGY_VERSION == "coverage-v1"


def test_all_surface_types() -> None:
    assert {s.value for s in SurfaceType} == {
        "repository",
        "database",
        "rag",
        "mcp",
        "browser_ai",
        "ai_agent",
    }


def test_nine_dimensions() -> None:
    assert len(list(CoverageDimension)) == 9


def test_surface_score_bounds() -> None:
    with pytest.raises(ValidationError):
        InventorySurface(
            surface_type=SurfaceType.REPOSITORY,
            external_or_resource_id="r",
            display_name="r",
            criticality=1.5,
            exposure_score=0.5,
            sensitivity_score=0.5,
            attack_likelihood=0.5,
            business_impact=0.5,
            risk_weight=1.0,
            inventory_confidence=0.5,
        )
