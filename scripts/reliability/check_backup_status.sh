#!/usr/bin/env bash
# Purpose: verify the latest PostgreSQL backup exists and is within the age policy. A "backup job
#   succeeded" signal is insufficient — this checks presence + age, and callers must additionally
#   run a real restore drill (verify_restore.sh).
# Env: DF_TARGET_ENV, DF_BACKUP_MAX_AGE_HOURS (default 24), DF_LATEST_BACKUP_EPOCH (unix seconds of
#   the newest backup, supplied by the backup provider integration). Never reads secrets.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

max_age="${DF_BACKUP_MAX_AGE_HOURS:-24}"
: "${DF_LATEST_BACKUP_EPOCH:?DF_LATEST_BACKUP_EPOCH must be provided by the backup provider}"
now="$(date +%s)"
age_hours=$(( (now - DF_LATEST_BACKUP_EPOCH) / 3600 ))

if (( age_hours > max_age )); then
  df_log "backup age ${age_hours}h exceeds policy ${max_age}h"
  df_result check_backup_status fail "{\"age_hours\":$age_hours,\"max_age_hours\":$max_age}"
  exit 1
fi
df_log "backup age ${age_hours}h within policy ${max_age}h"
df_result check_backup_status ok "{\"age_hours\":$age_hours,\"max_age_hours\":$max_age}"
