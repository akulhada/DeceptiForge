#!/usr/bin/env bash
# Purpose: verify a restored evidence object exists and its checksum matches the durable metadata.
# Env: DF_TARGET_ENV, DF_OBJECT_REF, DF_EXPECTED_SHA256, DF_ACTUAL_SHA256 (from the provider). Never
#   prints object contents or credentials.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
: "${DF_OBJECT_REF:?}"; : "${DF_EXPECTED_SHA256:?}"; : "${DF_ACTUAL_SHA256:?}"
if [[ "$DF_EXPECTED_SHA256" != "$DF_ACTUAL_SHA256" ]]; then
  df_log "checksum mismatch for $DF_OBJECT_REF"
  df_result verify_object_storage fail "{\"object\":\"$DF_OBJECT_REF\"}"
  exit 1
fi
df_result verify_object_storage ok "{\"object\":\"$DF_OBJECT_REF\"}"
