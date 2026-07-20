#!/usr/bin/env bash
# Purpose: promote the secondary region to primary AFTER the original primary is fenced. Refuses to
#   run unless fencing is confirmed (DF_PRIMARY_FENCED=true) — a secondary is never promoted while
#   the primary may still write.
# Env: DF_TARGET_ENV=production, DF_PRIMARY_FENCED, DF_NEW_EPOCH, DF_INCIDENT_ID.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
df_require_env production
: "${DF_INCIDENT_ID:?}"; : "${DF_NEW_EPOCH:?}"
if [[ "${DF_PRIMARY_FENCED:-false}" != "true" ]]; then
  df_log "REFUSING: primary is not confirmed fenced; cannot promote secondary"
  exit 3
fi
df_log "promoting secondary to primary at epoch $DF_NEW_EPOCH"
if df_dry_run; then df_result promote_secondary dry_run; exit 0; fi
: "${DF_APPLY_CMD:?config-apply command required to set the secondary to primary}"
eval "$DF_APPLY_CMD"
df_result promote_secondary ok "{\"incident\":\"$DF_INCIDENT_ID\",\"epoch\":$DF_NEW_EPOCH}"
