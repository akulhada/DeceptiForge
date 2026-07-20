# Purpose: orchestrate one deterministic coverage calculation into an immutable CoverageResult.
# Responsibilities: build the inventory, compute per-surface coverage, detect gaps, rank
#   recommendations, aggregate the risk-weighted overall score + confidence (unknown reported
#   separately, never counted as covered), count controls, and compute a stable source_state_hash so
#   identical state yields an identical snapshot. GPT never contributes. Bounded. Dependencies:
#   inventory, formula, blindspots, recommend, scoring, coverage domain, settings.
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.models.domain.coverage import (
    METHODOLOGY_VERSION,
    ControlStatus,
    ControlType,
    CoverageDimension,
    CoverageResult,
    SurfaceType,
)
from app.services.coverage_engine import blindspots, formula, recommend, scoring
from app.services.coverage_engine.inventory import SurfaceObservation, build_inventory


def _source_state_hash(observations: list[SurfaceObservation]) -> str:
    parts: list[str] = [METHODOLOGY_VERSION]
    for obs in sorted(
        observations,
        key=lambda o: (o.surface.surface_type.value, o.surface.external_or_resource_id),
    ):
        controls = sorted(
            f"{c.control_type.value}:{c.control_reference_id}:{c.status.value}"
            for c in obs.controls
        )
        parts.append(f"{obs.surface.surface_type.value}|{obs.surface.external_or_resource_id}|"
                     + ",".join(controls))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def calculate(
    session: Session, organization_id: UUID, settings: Settings, *, now: datetime | None = None
) -> CoverageResult:
    now = now or datetime.now(UTC)
    observations = build_inventory(session, organization_id, settings, now=now)

    # Cross-surface correlation is possible once two or more surface types carry an active decoy.
    surfaces_with_decoy: set[SurfaceType] = set()
    active_decoys = active_sensors = unhealthy_sensors = expired_decoys = 0
    for obs in observations:
        for c in obs.controls:
            if c.control_type == ControlType.DECOY and c.dimension == CoverageDimension.PLACEMENT:
                if c.status == ControlStatus.ACTIVE:
                    active_decoys += 1
                    surfaces_with_decoy.add(obs.surface.surface_type)
                elif c.status == ControlStatus.EXPIRED:
                    expired_decoys += 1
            if c.control_type == ControlType.SENSOR:
                if c.status == ControlStatus.ACTIVE:
                    active_sensors += 1
                elif c.status in (ControlStatus.DEGRADED, ControlStatus.FAILED):
                    unhealthy_sensors += 1
    cross_surface_present = len(surfaces_with_decoy) >= 2

    covered_weight = total_weight = unknown_weight = 0.0
    known_confidences: list[float] = []
    surfaces = []
    gaps_by_surface = []
    all_gaps = []
    for obs in observations:
        cov = formula.compute_surface_coverage(obs, cross_surface_present=cross_surface_present)
        surfaces.append(cov)
        if cov.is_unknown:
            unknown_weight += cov.surface.risk_weight
        else:
            total_weight += cov.surface.risk_weight
            covered_weight += cov.weighted_coverage
            known_confidences.append(cov.confidence)
        gaps = blindspots.detect_gaps(cov, obs)
        all_gaps += gaps
        gaps_by_surface.append((cov, gaps))

    overall = round(covered_weight / total_weight, 6) if total_weight > 0 else 0.0
    unknown_ratio = (
        unknown_weight / (total_weight + unknown_weight)
        if (total_weight + unknown_weight) > 0
        else 0.0
    )
    confidence = scoring.aggregate_confidence(known_confidences, unknown_ratio)

    recommendations = recommend.build_recommendations(
        gaps_by_surface, risk_tolerance=_risk_tolerance(session, organization_id),
        max_recommendations=settings.coverage_max_recommendations,
    )

    return CoverageResult(
        methodology_version=METHODOLOGY_VERSION, overall_score=scoring.clamp(overall),
        confidence=confidence, covered_weight=round(covered_weight, 6),
        total_weight=round(total_weight, 6), unknown_weight=round(unknown_weight, 6),
        active_decoys=active_decoys, active_sensors=active_sensors,
        unhealthy_sensors=unhealthy_sensors, expired_decoys=expired_decoys,
        blind_spot_count=len(all_gaps), source_state_hash=_source_state_hash(observations),
        surfaces=tuple(surfaces), gaps=tuple(all_gaps), recommendations=tuple(recommendations),
    )


def _risk_tolerance(session: Session, organization_id: UUID) -> float:
    import json

    from app.models.records import CoveragePolicyRecord

    record = session.scalars(
        select(CoveragePolicyRecord).where(
            CoveragePolicyRecord.organization_id == organization_id
        )
    ).first()
    if record is None:
        return 0.6
    data = json.loads(record.data or "{}")
    return float(data.get("recommendation_risk_tolerance", 0.6))
