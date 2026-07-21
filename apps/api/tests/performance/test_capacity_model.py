"""Fast regression guard for deterministic capacity arithmetic; no network or real tenant data."""

from __future__ import annotations

from app.services.capacity import TenantLimits


def test_small_tier_default_is_bounded() -> None:
    limits = TenantLimits("small", 20, 50, 1_000, 2, 2, 2)
    assert limits.monitoring_burst >= limits.monitoring_events_per_second
    assert limits.max_pending_jobs > 0
