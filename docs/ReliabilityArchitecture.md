<!-- Purpose: document the multi-region reliability architecture and data-class recovery objectives. -->

# Reliability architecture

DeceptiForge runs one active write region at a time with a warm-standby secondary. PostgreSQL is
authoritative for durable state; Redis is disposable coordination.

## Data classes and objectives (`app/models/domain/reliability.py`)

| Class | Examples | RPO | RTO |
|---|---|---|---|
| critical | organizations, identities, permissions, decoy deployments, monitoring events, alerts, incidents, evidence refs, audit | ≤ 5 min | ≤ 60 min |
| derived | coverage snapshots, recommendations, cached metadata, narratives, delivery projections | ≤ 24 h or recomputable | ≤ 4 h |
| ephemeral | Redis rate-limit counters, replay windows, caches | none | none |

Actual achieved values are measured per restore drill and are never claimed without a passing drill.

## Regions

Primary: web/API replicas, PostgreSQL primary + HA standby, Redis HA, worker pools, object/evidence
storage, KMS, monitoring. Secondary: warm application capacity, replicated/restorable PostgreSQL,
replicated/versioned evidence storage, KMS access plan, **schedulers disabled until promotion**.

Only the active write region may accept writes or run schedulers/side-effect workers
(`is_active_write_region`). This prevents dual schedulers, dual migrations, dual retention, dual
deployment workers, and split-brain SIEM delivery. See [DisasterRecovery](DisasterRecovery.md) and
[RegionalFailover](RegionalFailover.md).

## Runtime identity

`DEPLOYMENT_REGION`, `CLUSTER_ID`, `CLUSTER_ROLE` (primary/standby/recovery), `ACTIVE_REGION_EPOCH`,
`DEPLOYMENT_REVISION`, `DATABASE_CLUSTER_ID`. Ambiguous `CLUSTER_ROLE` is rejected at startup. Safe
values are exposed through `/admin/reliability/status` and `/ready`; infrastructure topology is not
exposed to tenant users.
