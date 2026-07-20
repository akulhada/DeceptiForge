#!/usr/bin/env bash
# Purpose: restore an encrypted PostgreSQL backup into an ISOLATED recovery database (never over
#   production). Supports point-in-time by replaying WAL where the provider supports it.
# Env: DF_TARGET_ENV=recovery (enforced), DF_RECOVERY_DATABASE_URL (isolated target),
#   DF_BACKUP_IDENTIFIER, optional DF_RECOVERY_POINT. Secrets are provided via the environment/KMS
#   and are never printed. Supports DF_DRY_RUN.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
df_require_env recovery

: "${DF_RECOVERY_DATABASE_URL:?isolated recovery database URL required}"
: "${DF_BACKUP_IDENTIFIER:?backup identifier required}"

df_log "restoring backup $DF_BACKUP_IDENTIFIER into the isolated recovery database"
if df_dry_run; then
  df_log "DRY RUN: would restore + replay WAL to ${DF_RECOVERY_POINT:-latest}"
  df_result restore_postgres dry_run "{\"backup\":\"$DF_BACKUP_IDENTIFIER\"}"
  exit 0
fi
# The concrete restore command is provider-specific (pg_restore / provider CLI). It must target
# ONLY $DF_RECOVERY_DATABASE_URL. This wrapper enforces the isolation env; the operator supplies the
# provider command via DF_RESTORE_CMD (which must reference the recovery URL).
: "${DF_RESTORE_CMD:?provider restore command required (must target the recovery database)}"
if [[ "$DF_RESTORE_CMD" != *"$DF_RECOVERY_DATABASE_URL"* ]]; then
  df_log "REFUSING: restore command does not target the isolated recovery database"
  exit 3
fi
eval "$DF_RESTORE_CMD"
df_result restore_postgres ok "{\"backup\":\"$DF_BACKUP_IDENTIFIER\"}"
