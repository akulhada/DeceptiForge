<!-- Purpose: the disaster-recovery boundary, principles, and split-brain protections. -->

# Disaster recovery

## Principles

PostgreSQL authoritative; Redis disposable; backups valid only when restored; failover preserves
organization isolation; encryption valid after restore; legal holds survive backup/restore/retention;
workers idempotent and recoverable; core ingestion fails safe; no silent data loss; no automatic
cross-region failover without split-brain protection; GPT is irrelevant to recovery.

## Split-brain protection

One active write region (`is_active_write_region`). Side-effect workers and schedulers gate on the
region and the active-region **epoch** (`app/services/reliability/fencing.py`): a promoted-but-stale
region is rejected. Approval of a failover advances to `PRIMARY_FENCED` before any promotion, so a
secondary is never promoted while the primary may still write. Migration/deployment/retention run
only on the active region.

## Controlled failover / failback

Failover is a declared-incident, operator-approved, audited state machine
([RegionalFailover](RegionalFailover.md)); failback is manual and gated on validated resync
([RegionalFailback](RegionalFailback.md)). Degraded modes are explicit
([DegradedModes](DegradedModes.md)). Encryption-key recovery: [EncryptionKeyRecovery](EncryptionKeyRecovery.md).
