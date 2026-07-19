#!/usr/bin/env bash
# Purpose: validate a controlled-staging configuration BEFORE deployment.
# Behavior: checks required environment variables are present and safe, renders the production
#   Compose file, asserts no private-service host ports, and runs application settings validation.
#   Prints only presence/validity — never secret values. Exits non-zero on any unsafe setting.
#
# shellcheck disable=SC2015  # `grep && ok || bad`: ok/bad always return 0, intentional reporting.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$REPO_ROOT/docker-compose.prod.example.yml}"
API_DIR="$REPO_ROOT/apps/api"
fail=0

say()  { printf '  %-42s %s\n' "$1" "$2"; }
bad()  { say "$1" "FAIL: $2"; fail=1; }
ok()   { say "$1" "ok"; }

# present KEY -> ok if set & non-empty (value never printed)
present() {
  local key="$1"
  if [ -n "${!key:-}" ]; then ok "$key present"; else bad "$key present" "unset/empty"; fi
}

# expect KEY VALUE -> ok if env value equals VALUE exactly
expect() {
  local key="$1" want="$2" got="${!1:-}"
  if [ "$got" = "$want" ]; then ok "$key=$want"; else bad "$key=$want" "got a different value"; fi
}

echo "== staging preflight =="

echo "-- required environment --"
for v in DATABASE_URL REDIS_URL EVIDENCE_ENCRYPTION_KEY CORS_ORIGINS; do present "$v"; done

echo "-- production-shaped settings --"
expect APP_ENV staging
expect AUTH_ENABLED true
expect DEMO_ENABLED false
expect MONITOR_SIGNATURE_REQUIRED true
expect RATE_LIMIT_BACKEND redis
expect REPLAY_BACKEND redis
expect EVIDENCE_ENCRYPTION_MODE local

echo "-- bootstrap keys disabled --"
if [ "${BOOTSTRAP_KEYS_ENABLED:-false}" = "true" ]; then
  bad "BOOTSTRAP_KEYS_ENABLED" "must be false in steady state"
else
  ok "BOOTSTRAP_KEYS_ENABLED not active"
fi

echo "-- CORS is explicit (no wildcard) --"
case "${CORS_ORIGINS:-}" in
  ""|"[]") bad "CORS_ORIGINS explicit" "empty" ;;
  *"*"*)   bad "CORS_ORIGINS explicit" "wildcard not allowed" ;;
  *)       ok "CORS_ORIGINS explicit" ;;
esac

echo "-- production Compose renders --"
if command -v docker >/dev/null 2>&1; then
  if docker compose -f "$COMPOSE_FILE" config >/tmp/df_compose_rendered.yml 2>/dev/null; then
    ok "compose config renders"
    if grep -Eq '^\s+- (published|target): "?(5432|6379)"?' /tmp/df_compose_rendered.yml \
       || grep -Eq '"(5432|6379):(5432|6379)"|(5432|6379):(5432|6379)' /tmp/df_compose_rendered.yml; then
      bad "no private host ports" "postgres/redis port published"
    else
      ok "no postgres/redis host ports"
    fi
    grep -q "MONITOR_SIGNATURE_REQUIRED" /tmp/df_compose_rendered.yml \
      && ok "compose sets monitor signatures" \
      || bad "compose sets monitor signatures" "missing"
    rm -f /tmp/df_compose_rendered.yml
  else
    bad "compose config renders" "render failed (set required compose vars)"
  fi
else
  say "docker" "SKIP: docker CLI unavailable (validate in CI/target host)"
fi

echo "-- application settings validation --"
if command -v python >/dev/null 2>&1 && [ -d "$API_DIR" ]; then
  if (cd "$API_DIR" && python -c "from app.config.settings import Settings; Settings().validate_runtime()") 2>/tmp/df_validate.err; then
    ok "Settings.validate_runtime()"
  else
    # Print only the safe error message (no environment dump).
    bad "Settings.validate_runtime()" "$(tail -n1 /tmp/df_validate.err | cut -c1-120)"
  fi
  rm -f /tmp/df_validate.err
else
  say "python" "SKIP: python/app unavailable (validate on target host)"
fi

echo
if [ "$fail" -ne 0 ]; then
  echo "PREFLIGHT: FAIL — do not deploy until every item is ok."
  exit 1
fi
echo "PREFLIGHT: PASS"
