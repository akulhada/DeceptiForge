"""Tenant quotas, bounded queue admission, usage snapshots, and measured capacity estimates."""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass
from uuid import UUID

from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.models.records import (
    AlertRecord,
    DetectionEventRecord,
    PerformanceRunRecord,
    ReconstructionJobRecord,
    RepositoryRecord,
    TenantLimitRecord,
)
from app.services.redis_support import RedisClient, build_redis_client


@dataclass(frozen=True)
class TenantLimits:
    tier: str
    monitoring_events_per_second: int
    monitoring_burst: int
    max_pending_jobs: int
    max_concurrent_scans: int
    max_concurrent_deployments: int
    max_report_jobs: int


@dataclass(frozen=True)
class QuotaDecision:
    accepted: bool
    retry_after_seconds: int
    reason: str | None = None


@dataclass(frozen=True)
class QueueSnapshot:
    queue: str
    pending_count: int
    oldest_age_seconds: int
    processing_count: int
    projected_drain_seconds: int | None


def defaults(settings: Settings) -> TenantLimits:
    return TenantLimits(
        tier=settings.default_tenant_tier,
        monitoring_events_per_second=settings.monitoring_max_events_per_second,
        monitoring_burst=settings.monitoring_max_burst,
        max_pending_jobs=settings.tenant_max_pending_jobs,
        max_concurrent_scans=settings.tenant_max_concurrent_scans,
        max_concurrent_deployments=settings.tenant_max_concurrent_deployments,
        max_report_jobs=settings.tenant_max_report_jobs,
    )


class TenantCapacityService:
    """Small persistence boundary for tenant limits and bounded capacity snapshots."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def limits(self, organization_id: UUID) -> TenantLimits:
        row = self._session.scalar(
            select(TenantLimitRecord).where(TenantLimitRecord.organization_id == organization_id)
        )
        if row is None:
            return defaults(self._settings)
        return TenantLimits(
            tier=row.tier,
            monitoring_events_per_second=row.monitoring_events_per_second,
            monitoring_burst=row.monitoring_burst,
            max_pending_jobs=row.max_pending_jobs,
            max_concurrent_scans=row.max_concurrent_scans,
            max_concurrent_deployments=row.max_concurrent_deployments,
            max_report_jobs=row.max_report_jobs,
        )

    def set_limits(
        self, organization_id: UUID, limits: TenantLimits, actor_id: UUID | None
    ) -> TenantLimits:
        _validate(limits)
        row = self._session.scalar(
            select(TenantLimitRecord).where(TenantLimitRecord.organization_id == organization_id)
        )
        if row is None:
            row = TenantLimitRecord(organization_id=organization_id, **asdict(limits))
            self._session.add(row)
        else:
            for field, value in asdict(limits).items():
                setattr(row, field, value)
            row.version += 1
        row.updated_by_actor_id = actor_id
        self._session.flush()
        return self.limits(organization_id)

    def usage(self, organization_id: UUID) -> dict[str, int | str]:
        """Bounded scalar counts; dashboard detail endpoints must paginate separately."""
        return {
            "tier": self.limits(organization_id).tier,
            "monitoring_events": self._count(DetectionEventRecord, organization_id),
            "alerts": self._count(AlertRecord, organization_id),
            "repositories": self._count(RepositoryRecord, organization_id),
            "pending_reconstruction_jobs": self._count(
                ReconstructionJobRecord, organization_id, status="pending"
            ),
        }

    def queue_snapshot(self, organization_id: UUID | None = None) -> QueueSnapshot:
        query = select(ReconstructionJobRecord).where(ReconstructionJobRecord.status == "pending")
        if organization_id is not None:
            query = query.where(ReconstructionJobRecord.organization_id == organization_id)
        pending = self._session.scalars(
            query.order_by(ReconstructionJobRecord.created_at).limit(1)
        ).first()
        count_query = select(func.count()).select_from(ReconstructionJobRecord).where(
            ReconstructionJobRecord.status == "pending"
        )
        processing_query = select(func.count()).select_from(ReconstructionJobRecord).where(
            ReconstructionJobRecord.status == "claimed"
        )
        if organization_id is not None:
            count_query = count_query.where(
                ReconstructionJobRecord.organization_id == organization_id
            )
            processing_query = processing_query.where(
                ReconstructionJobRecord.organization_id == organization_id
            )
        count = int(self._session.scalar(count_query) or 0)
        processing = int(self._session.scalar(processing_query) or 0)
        age = 0 if pending is None else max(0, int(time.time() - pending.created_at.timestamp()))
        # A drain estimate needs a measured throughput coefficient; never invent one from depth.
        return QueueSnapshot("reconstruction", count, age, processing, None)

    def top_tenants(self, limit: int = 100) -> tuple[dict[str, object], ...]:
        """Bounded global usage view for platform operators; never exposed to tenant roles."""
        rows = self._session.execute(
            select(
                DetectionEventRecord.organization_id,
                func.count(DetectionEventRecord.id).label("events"),
            )
            .group_by(DetectionEventRecord.organization_id)
            .order_by(func.count(DetectionEventRecord.id).desc())
            .limit(limit)
        ).all()
        return tuple(
            {"organization_id": str(row.organization_id), "monitoring_events": int(row.events)}
            for row in rows
        )

    def _count(
        self, model: type[object], organization_id: UUID, *, status: str | None = None
    ) -> int:
        organization = model.organization_id  # type: ignore[attr-defined]
        query = select(func.count()).select_from(model).where(organization == organization_id)
        if status is not None:
            query = query.where(model.status == status)  # type: ignore[attr-defined]
        return int(self._session.scalar(query) or 0)

    def latest_performance_run(self) -> PerformanceRunRecord | None:
        return self._session.scalar(
            select(PerformanceRunRecord)
            .where(PerformanceRunRecord.status == "passed")
            .order_by(PerformanceRunRecord.created_at.desc())
        )

    def recommendations(self) -> dict[str, object]:
        run = self.latest_performance_run()
        if run is None:
            return {"status": "uncertified", "recommendations": []}
        results = json.loads(run.results)
        throughput = float(results.get("monitoring_events_per_second", 0))
        if throughput <= 0:
            return {"status": "insufficient_measurements", "recommendations": []}
        headroom = 1 + self._settings.capacity_headroom_percent / 100
        target = self._settings.monitoring_max_events_per_second
        replicas = max(1, int((target * headroom + throughput - 1) // throughput))
        return {
            "status": "measured",
            "methodology_version": run.methodology_version,
            "recommendations": [
                {
                    "workload": "monitoring_ingest",
                    "measured_events_per_second_per_replica": throughput,
                    "recommended_api_replicas": replicas,
                    "headroom_percent": self._settings.capacity_headroom_percent,
                }
            ],
        }


class MonitoringQuotaGate:
    """Per-organization fixed-window admission with a short burst bucket and bounded Redis keys."""

    _lock = threading.Lock()
    _memory: dict[str, tuple[int, int]] = {}

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._redis: RedisClient | None = (
            build_redis_client(settings) if settings.rate_limit_backend == "redis" else None
        )

    def admit(self, organization_id: UUID, limits: TenantLimits) -> QuotaDecision:
        now = time.time()
        second = int(now)
        minute = int(now // 60)
        prefix = f"{self._settings.redis_key_prefix}:quota:monitor:{organization_id}"
        try:
            burst = self._increment(f"{prefix}:s:{second}", 2)
            sustained = self._increment(f"{prefix}:m:{minute}", 61)
        except (RedisError, OSError):
            return QuotaDecision(False, 1, "quota_store_unavailable")
        if burst > limits.monitoring_burst:
            return QuotaDecision(False, 1, "burst_limit")
        if sustained > limits.monitoring_events_per_second * 60:
            return QuotaDecision(False, max(1, 60 - int(now % 60)), "sustained_limit")
        return QuotaDecision(True, 0)

    def _increment(self, key: str, ttl: int) -> int:
        if self._redis is not None:
            value = int(self._redis.incr(key))
            if value == 1:
                self._redis.expire(key, ttl)
            return value
        with self._lock:
            now = int(time.time())
            value, expiry = self._memory.get(key, (0, now + ttl))
            if expiry <= now:
                value, expiry = 0, now + ttl
            self._memory[key] = (value + 1, expiry)
            return value + 1


def _validate(limits: TenantLimits) -> None:
    if limits.tier not in {"small", "medium", "large"}:
        raise ValueError("invalid tenant tier")
    values = asdict(limits)
    if any(value <= 0 for key, value in values.items() if key != "tier"):
        raise ValueError("tenant limits must be positive")
    if limits.monitoring_burst < limits.monitoring_events_per_second:
        raise ValueError("monitoring burst must be at least events per second")
