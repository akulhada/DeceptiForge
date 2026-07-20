<!-- Purpose: PostgreSQL + object-storage backup policy. -->

# Backup policy

Backups are not valid until restored and verified (see [RestoreDrills](RestoreDrills.md)).

## PostgreSQL

Encrypted full backups + continuous WAL archiving for point-in-time recovery (provider-dependent),
with retention tiers, integrity checks, cross-region copy, deletion protection, and failed-backup
alerts. Backups include the application schema + migration revision, organization/identity/RBAC
state, audit history, legal holds, encrypted metadata, worker/outbox state, and connector
configuration references — but **never** plaintext secrets (secrets stay in KMS/secret manager).
`backup_metadata` (`app/services/reliability/backup_meta.py`) records only schema shape + migration,
and `assert_no_secrets` guards against leaking a secret value into the inventory.

## Object / evidence storage

Encryption at rest, versioning, object lock where legal hold requires it, cross-region replication,
restricted deletion, checksum validation, immutable metadata in PostgreSQL, and replication-failure
alerts. See [runbooks/ObjectStorageFailure](runbooks/ObjectStorageFailure.md).

## Verification cadence

Daily backup age check (`scripts/reliability/check_backup_status.sh`) — a "job succeeded" signal is
insufficient; weekly isolated restore; monthly application-level drill; quarterly regional exercise.
