#!/usr/bin/env bash
# Purpose: fence the primary region before promoting a secondary (split-brain prevention). Sets the
#   primary to maintenance/standby and bumps the active-region epoch so stale side-effect workers
#   are rejected. Requires an authorized operator and a declared incident.
# Env: DF_TARGET_ENV=production, DF_INCIDENT_ID, DF_NEW_EPOCH. Does NOT itself promote a secondary.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
df_require_env production
: "${DF_INCIDENT_ID:?a declared incident id is required to fence the primary}"
: "${DF_NEW_EPOCH:?new active-region epoch required}"
df_log "fencing primary for incident $DF_INCIDENT_ID; new epoch $DF_NEW_EPOCH"
if df_dry_run; then df_result fence_primary dry_run; exit 0; fi
# Apply CLUSTER_ROLE=standby + MAINTENANCE_MODE=true + ACTIVE_REGION_EPOCH bump to the primary
# deployment (provider-specific config apply). Fail closed on any error.
: "${DF_APPLY_CMD:?config-apply command required to set the primary to standby/maintenance}"
eval "$DF_APPLY_CMD"
df_result fence_primary ok "{\"incident\":\"$DF_INCIDENT_ID\",\"epoch\":$DF_NEW_EPOCH}"
