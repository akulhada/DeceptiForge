<!-- Purpose: deterministic PostgreSQL restore + verification procedure. -->

# PostgreSQL recovery

Never restore over production during routine testing. Restore into an isolated recovery database.

## Procedure

1. Select a backup or point in time.
2. Provision an isolated recovery database (`CLUSTER_ROLE=recovery`).
3. Restore the encrypted backup (`scripts/reliability/restore_postgres.sh`, `DF_TARGET_ENV=recovery`).
4. Replay WAL for point-in-time where supported.
5. Validate PostgreSQL version + extensions; confirm migration revision.
6. Run integrity checks (`scripts/reliability/verify_restore.sh`).
7. Verify organization isolation, legal holds, audit, encryption-key references.
8. Run application smoke tests.
9. Produce a checksummed restore report; record achieved RPO/RTO.
10. Destroy the isolated recovery environment after the retention period.

## Integrity checks (`app/services/reliability/restore_verify.py`)

Required tables present · migration revision matches head · org-scope columns present · encryption
round-trip (old records decryptable) · stale delivery leases reclaimable · plausible row counts ·
legal-hold presence (pass-if-not-modeled). Each drill records exact checks + results, checksummed.
