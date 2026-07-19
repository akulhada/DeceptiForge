# Bootstrap keys and evidence encryption

## Bootstrap API keys

Environment bindings (`API_KEY_BINDINGS`) mint owner-scoped access without a database row. They are
**disabled by default** and exist only to create the first DB-backed owner key. They never grant
implicit permanent access, and every use is written to the security audit log
(`bootstrap_auth_used`).

Production refuses to start if bootstrap keys are enabled with bindings but **no expiry**
(`BOOTSTRAP_EXPIRES_AT` unset) — an unrestricted permanent bootstrap key is not permitted.

### Procedure

1. Temporarily open a time-boxed window:
   `BOOTSTRAP_KEYS_ENABLED=true`, `BOOTSTRAP_EXPIRES_AT=<near-future ISO-8601>`,
   `API_KEY_BINDINGS='{"<secret>": "<org-uuid>"}'`.
2. Call `POST /admin/api-keys` (role `owner`) with the bootstrap key to mint the first DB-backed
   owner key. Store the returned plaintext once.
3. Set `BOOTSTRAP_KEYS_ENABLED=false` and remove `API_KEY_BINDINGS`.
4. Restart. From now on authenticate with the DB-backed key.

Bootstrap authentication is rejected once the window is disabled or `BOOTSTRAP_EXPIRES_AT` passes.

## Evidence encryption

Evidence-bearing blobs (detection events, alerts, incidents) are encrypted at rest through an
`EncryptionProvider` before persistence, and the key version is stored with each ciphertext so keys
can be rotated. Decrypted evidence is never logged.

`EVIDENCE_ENCRYPTION_MODE`:

| Mode | Use | Behavior |
| --- | --- | --- |
| `disabled` | development only | reversible encoding, **not** encryption; production refuses to start |
| `local` | app-managed key | Fernet (AES-CBC + HMAC) authenticated encryption from `EVIDENCE_ENCRYPTION_KEY` |

Production must set an explicit mode. For a managed KMS/envelope strategy, implement an
`EncryptionProvider` that wraps the data key with the KMS and set the mode accordingly; the storage
format (`<mode>:<key_version>:<payload>`) already carries the version needed for rotation. Rows
written before encryption (legacy plaintext JSON) are still readable and are re-sealed on next write.
