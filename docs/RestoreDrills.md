<!-- Purpose: restore-drill cadence, recording, and staging certification. -->

# Restore drills

A backup dashboard based only on "backup job succeeded" is insufficient. Drills prove recoverability.

## Cadence

Daily backup verification · weekly isolated database restore · monthly application-level recovery
drill · quarterly regional failover exercise.

## Each drill records

Backup selected, recovery point, start/end, achieved RPO, achieved RTO, validation results,
failures, remediation owner, and an evidence reference — persisted in `restore_drills` with a
checksummed report (no secrets). Run via `POST /admin/reliability/restore-drills`
(`restore_drills:run`, gated on `RESTORE_DRILL_ENABLED`) or `scripts/reliability/verify_restore.sh`.

## Staging certification

Confirm backup → restore into isolation → validate migration/isolation/encryption/legal-holds →
start app → health/readiness → ingest a signed monitoring event → reconstruct an incident →
generate an evidence package → deliver a mock SIEM event → verify object storage → record RPO/RTO →
store drill evidence. Then a regional rehearsal (fence primary, promote secondary, transfer
leadership, redirect traffic, smoke test, no duplicate operations, documented failback).
