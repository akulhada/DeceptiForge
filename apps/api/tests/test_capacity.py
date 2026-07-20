"""Deterministic unit coverage for tenant limits, quota backpressure, and measured estimates."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import Settings
from app.database.base import Base
from app.models import records as _records  # noqa: F401
from app.models.records import PerformanceRunRecord, ReconstructionJobRecord
from app.repositories.artifacts import ArtifactRepository
from app.services.capacity import MonitoringQuotaGate, TenantCapacityService, TenantLimits

_DB_URL = "postgresql+psycopg://unused:unused@localhost/deceptiforge"


def _settings(**values: object) -> Settings:
    return Settings(_env_file=None, database_url=_DB_URL, **values)  # type: ignore[call-arg]


def _session():  # type: ignore[no-untyped-def]
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_tenant_limits_are_isolated_and_usage_is_scoped() -> None:
    session = _session()
    service = TenantCapacityService(session, _settings())
    org_a, org_b = uuid4(), uuid4()
    updated = service.set_limits(
        org_a,
        TenantLimits("medium", 30, 60, 70, 2, 2, 2),
        None,
    )

    assert updated.max_pending_jobs == 70
    assert service.limits(org_b).tier == "small"
    assert service.usage(org_a)["monitoring_events"] == 0
    assert service.usage(org_b)["pending_reconstruction_jobs"] == 0


def test_burst_quota_returns_retryable_backpressure() -> None:
    settings = _settings(rate_limit_backend="memory")
    gate = MonitoringQuotaGate(settings)
    limits = TenantLimits("small", 1, 2, 10, 1, 1, 1)
    org = uuid4()

    assert gate.admit(org, limits).accepted
    assert gate.admit(org, limits).accepted
    rejected = gate.admit(org, limits)
    assert not rejected.accepted
    assert rejected.reason == "burst_limit"
    assert rejected.retry_after_seconds >= 1


def test_capacity_recommendation_uses_only_measured_run_coefficients() -> None:
    session = _session()
    settings = _settings(monitoring_max_events_per_second=20, capacity_headroom_percent=50)
    service = TenantCapacityService(session, settings)
    assert service.recommendations()["status"] == "uncertified"
    session.add(
        PerformanceRunRecord(
            methodology_version="performance-v1",
            code_revision="test",
            infrastructure=json.dumps({"api_replicas": 1}),
            workload=json.dumps({"tier": "small"}),
            results=json.dumps({"monitoring_events_per_second": 10}),
            status="passed",
        )
    )
    session.flush()

    recommendation = service.recommendations()
    assert recommendation["status"] == "measured"
    item = recommendation["recommendations"][0]
    assert item["recommended_api_replicas"] == 3


def test_reconstruction_claim_reserves_one_fair_share_per_tenant() -> None:
    session = _session()
    now = datetime.now(UTC)
    large, small = uuid4(), uuid4()
    for organization_id in (large, large, large, small):
        session.add(
            ReconstructionJobRecord(
                organization_id=organization_id,
                status="pending",
                trace_identifier="DFG-test",
                decoy_id=uuid4(),
                window_start=now,
                window_end=now,
            )
        )
    session.flush()

    claimed = ArtifactRepository(session).claim_reconstruction_jobs(2)
    assert {job.organization_id for job in claimed} == {large, small}
