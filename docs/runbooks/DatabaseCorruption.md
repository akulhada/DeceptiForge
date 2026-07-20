<!-- Runbook: suspected database corruption. -->

# Runbook: database corruption

1. Stop writes (`MAINTENANCE_MODE=true` on the active region).
2. Declare an incident; capture the suspected corruption scope.
3. Select a clean backup / point in time before the corruption.
4. Restore into an isolated recovery database (`restore_postgres.sh`, `DF_TARGET_ENV=recovery`).
5. Run `verify_restore.sh` — confirm tables, migration, org isolation, encryption, row counts.
6. Only after a passing drill, cut over to the restored database (treat as a failover).
7. Record RPO/RTO and remediation; never restore over production during verification.
