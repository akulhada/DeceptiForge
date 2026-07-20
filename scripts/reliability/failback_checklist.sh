#!/usr/bin/env bash
# Purpose: enforce the manual failback checklist ordering. Failback is NEVER automatic. Refuses to
#   proceed unless the original region is resynchronized and validated.
# Env: DF_TARGET_ENV=production, DF_RESYNC_VALIDATED, DF_INCIDENT_ID.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
df_require_env production
: "${DF_INCIDENT_ID:?}"
if [[ "${DF_RESYNC_VALIDATED:-false}" != "true" ]]; then
  df_log "REFUSING: failback cannot start before database + object-storage resync is validated"
  exit 3
fi
df_log "failback preconditions met for incident $DF_INCIDENT_ID; proceed via RegionalFailback.md"
df_result failback_checklist ok "{\"incident\":\"$DF_INCIDENT_ID\"}"
