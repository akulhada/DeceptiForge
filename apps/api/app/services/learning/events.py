# Purpose: stable identity for immutable learning events.
# Responsibilities: derive a deterministic event hash so the same observation recorded twice is a
#   no-op, while a correction (different payload) appends a new event. Hash inputs are identifiers,
#   enumerations, and timestamps only — never content. Dependencies: stdlib. No I/O.
from __future__ import annotations

import hashlib
from datetime import datetime
from uuid import UUID


def learning_event_hash(
    *,
    organization_id: UUID,
    event_type: str,
    occurred_at: datetime,
    feature_snapshot_id: UUID | None = None,
    recommendation_id: UUID | None = None,
    placement_outcome_id: UUID | None = None,
    analyst_feedback_id: UUID | None = None,
    operational_result_id: UUID | None = None,
    source_event_id: UUID | None = None,
) -> str:
    """Deterministic identity for an event. Duplicate submissions collapse; corrections do not."""
    parts = (
        str(organization_id),
        event_type,
        occurred_at.isoformat(),
        str(feature_snapshot_id or "-"),
        str(recommendation_id or "-"),
        str(placement_outcome_id or "-"),
        str(analyst_feedback_id or "-"),
        str(operational_result_id or "-"),
        str(source_event_id or "-"),
    )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
