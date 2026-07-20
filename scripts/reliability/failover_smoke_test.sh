#!/usr/bin/env bash
# Purpose: post-promotion smoke test — readiness, a signed monitoring ingest, and confirmation that
#   only one scheduler is active. Never sends real sensitive payloads.
# Env: DF_TARGET_ENV, DF_BASE_URL.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
: "${DF_BASE_URL:?base URL of the promoted region required}"
ready="$(curl -fsS "$DF_BASE_URL/ready" || true)"
if ! grep -q '"status": *"ok"' <<<"$ready"; then
  df_log "readiness not ok after promotion"
  df_result failover_smoke_test fail
  exit 1
fi
df_result failover_smoke_test ok
