<!-- Purpose: PostgreSQL + object-storage backup policy. -->

# Backup policy

Backups are not valid until restored and verified (see [RestoreDrills](RestoreDrills.md)).

## PostgreSQL

Encrypted full backups + continuous WAL archiving for point-in-time recovery (provider-dependent),
with retention tiers, integrity checks, cross-region copy, deletion protection, and failed-backup
alerts. Backups include the application schema + migration revision, organization/identity/RBAC
state, audit history, encrypted metadata, worker/outbox state, and connector
configuration references — but **never** plaintext secrets (secrets stay in KMS/secret manager).
`backup_metadata` (`app/services/reliability/backup_meta.py`) records only schema shape + migration,
and `assert_no_secrets` guards against leaking a secret value into the inventory.

## Object / evidence storage

Encryption at rest, versioning, cross-region replication,
restricted deletion, checksum validation, immutable metadata in PostgreSQL, and replication-failure
alerts. See [runbooks/ObjectStorageFailure](runbooks/ObjectStorageFailure.md).

## Verification cadence

Daily backup age check (`scripts/reliability/check_backup_status.sh`) — a "job succeeded" signal is
insufficient; weekly isolated restore; monthly application-level drill; quarterly regional exercise.

## Legal holds (not implemented)

DeceptiForge does **not** implement legal holds. There is no organization-scoped hold model, and no
retention, lifecycle, or deletion path consults one — so no record is exempt from retention today.
The restore drill deliberately makes no legal-hold claim; a check that reported holds as present
would have certified preservation that does not exist.

Implementing them requires all of: an organization-scoped hold model, enforcement in every deletion
and retention path (`app/jobs/retention.py`, `app/jobs/incident_lifecycle.py`, agent and learning
retention), and a restore-drill check that fails when a held record is missing. Until that exists,
no document, drill, or product surface may claim hold preservation.
