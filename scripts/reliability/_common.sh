#!/usr/bin/env bash
# Purpose: shared helpers for reliability scripts. Sourced, not executed.
# Behavior: strict mode, a correlation id, machine-readable result emission, secret-free logging,
#   and an environment guard that refuses to run a production action against a dev/test target and
#   vice versa. Never prints secrets.
set -euo pipefail

DF_CORRELATION_ID="${DF_CORRELATION_ID:-$(date +%s)-$RANDOM}"
DF_RESULT_DIR="${DF_RESULT_DIR:-/tmp/deceptiforge-reliability}"
mkdir -p "$DF_RESULT_DIR"

df_log() { printf '[%s] %s\n' "$DF_CORRELATION_ID" "$*" >&2; }

# Emit a machine-readable JSON result file and echo its path.
df_result() { # df_result <name> <status> [extra_json]
  local name="$1" status="$2" extra="${3:-{}}"
  local out="$DF_RESULT_DIR/${name}-${DF_CORRELATION_ID}.json"
  printf '{"script":"%s","status":"%s","correlation_id":"%s","extra":%s}\n' \
    "$name" "$status" "$DF_CORRELATION_ID" "$extra" > "$out"
  echo "$out"
}

# Refuse to act on the wrong environment. Requires DF_TARGET_ENV and DF_EXPECT_ENV to match.
df_require_env() { # df_require_env <expected>
  local expected="$1"
  : "${DF_TARGET_ENV:?DF_TARGET_ENV must be set (development|staging|production)}"
  if [[ "$DF_TARGET_ENV" != "$expected" ]]; then
    df_log "REFUSING: this action requires DF_TARGET_ENV=$expected, got $DF_TARGET_ENV"
    exit 3
  fi
}

df_dry_run() { [[ "${DF_DRY_RUN:-false}" == "true" ]]; }
