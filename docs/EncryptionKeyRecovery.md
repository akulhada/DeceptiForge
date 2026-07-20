<!-- Purpose: encryption + key recovery requirements and testing. -->

# Encryption & key recovery

Recovery is tested for database, evidence, connector-secret, backup, object-storage, signing,
webhook, and session encryption/keys.

## Requirements

- Keys are **not** embedded in backups (secrets stay in KMS/secret manager).
- The secondary region has controlled, least-privilege KMS access.
- Key versions are retained so key rotation never makes old backups/records unreadable.
- Break-glass key recovery is audited.
- Restore drills verify old encrypted records remain decryptable (`encryption_readable` check in
  `restore_verify`).

Never export raw master keys into documentation or backup bundles.
