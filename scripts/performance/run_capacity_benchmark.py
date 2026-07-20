"""Run a deterministic local quota benchmark and emit a certification-ready synthetic result."""
from __future__ import annotations

import json
import time
from statistics import quantiles
from uuid import uuid4

from app.config.settings import Settings
from app.services.capacity import MonitoringQuotaGate, TenantLimits


def main() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://unused:unused@localhost/deceptiforge",
        rate_limit_backend="memory",
    )
    gate = MonitoringQuotaGate(settings)
    limits = TenantLimits("small", 100_000, 100_000, 1_000, 2, 2, 2)
    organization_id = uuid4()
    samples: list[float] = []
    started = time.perf_counter()
    for _ in range(1_000):
        before = time.perf_counter()
        assert gate.admit(organization_id, limits).accepted
        samples.append((time.perf_counter() - before) * 1_000)
    elapsed = time.perf_counter() - started
    p95 = quantiles(samples, n=100)[94]
    print(
        json.dumps(
            {
                "methodology_version": "performance-v1",
                "synthetic": True,
                "workload": "monitoring_quota_admission",
                "operations": 1_000,
                "monitoring_events_per_second": round(1_000 / elapsed, 2),
                "p95_ms": round(p95, 4),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
