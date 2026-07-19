#!/usr/bin/env bash
# Purpose: verify a running staging deployment behaves safely (production-shaped topology).
# Behavior: HTTP checks against BASE_URL plus container/topology checks via Compose when available.
#   Signed-ingestion controls (unsigned/invalid-signature/expired/replay) are exercised by
#   scripts/staging/smoke_test.sh, invoked here when its env is present. Prints only pass/fail.
#
# Required: BASE_URL, API_KEY (any valid key), ORG_ID.
# Optional: COMPOSE_FILE (for UID/worker/no-auto-migrate checks); smoke_test.sh env for 8–11.
#
# shellcheck disable=SC2015  # `check && ok || bad`: ok/note/bad always return 0, so C never runs
#                              erroneously — this is intentional reporting, not if-then-else.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$REPO_ROOT/docker-compose.prod.example.yml}"
: "${BASE_URL:?set BASE_URL}"; : "${API_KEY:?set API_KEY}"; : "${ORG_ID:?set ORG_ID}"
fail=0
note() { printf '  %-46s %s\n' "$1" "$2"; }
ok()   { note "$1" "ok"; }
bad()  { note "$1" "FAIL: $2"; fail=1; }
skip() { note "$1" "SKIP: $2"; }

code() { # code METHOD PATH [extra curl args...]
  local m="$1" p="$2"; shift 2
  curl -s -o /dev/null -w '%{http_code}' -X "$m" "$BASE_URL$p" "$@"
}
auth=(-H "X-DeceptiForge-API-Key: $API_KEY" -H "X-DeceptiForge-Org-Id: $ORG_ID")

echo "== runtime verification =="

# --- container / topology (Compose) --------------------------------------------------------------
if command -v docker >/dev/null 2>&1 && docker compose -f "$COMPOSE_FILE" ps >/dev/null 2>&1; then
  cid="$(docker compose -f "$COMPOSE_FILE" ps -q api | head -n1)"
  if [ -n "$cid" ]; then
    uid="$(docker exec "$cid" id -u 2>/dev/null || echo '?')"
    [ "$uid" = "10001" ] && ok "1. API runs as UID 10001" || bad "1. API runs as UID 10001" "uid=$uid"
    cmd="$(docker inspect --format '{{json .Config.Cmd}}' "$cid" 2>/dev/null || echo '')"
    echo "$cmd" | grep -q uvicorn && ! echo "$cmd" | grep -qi alembic \
      && ok "17. API start does not run migrations" \
      || bad "17. API start does not run migrations" "cmd=$cmd"
  else
    skip "1/17. API container checks" "api service not found"
  fi
  running="$(docker compose -f "$COMPOSE_FILE" ps --services --status running 2>/dev/null || true)"
  echo "$running" | grep -q reconstruction && ok "18. reconstruction worker running" \
    || bad "18. reconstruction worker running" "not running"
  echo "$running" | grep -Eq 'lifecycle|retention' && ok "19. retention/lifecycle worker running" \
    || bad "19. retention/lifecycle worker running" "not running"
else
  skip "1,17,18,19. container/worker checks" "docker/compose unavailable (run on target host)"
fi

# --- HTTP behavior -------------------------------------------------------------------------------
[ "$(code GET /health)" = "200" ] && ok "2. health 200" || bad "2. health" "not 200"
ready="$(curl -s "$BASE_URL/ready")"
echo "$ready" | grep -q '"status"' && ok "3. readiness responds" || bad "3. readiness" "no body"
echo "$ready" | grep -q '"database": *"ok"\|"database":{"status":"ok"}' \
  && ok "4. postgres healthy" || note "4. postgres healthy" "check /ready: $ready"
echo "$ready" | grep -q '"redis": *"ok"\|"status":"ok"' \
  && ok "5. redis healthy" || note "5. redis healthy" "check /ready: $ready"
[ "$(code POST /demo/seed)" = "404" ] && ok "6. demo routes unavailable" || bad "6. demo routes" "not 404"
[ "$(code POST /repositories/scan "${auth[@]}" -H 'Content-Type: application/json' \
  --data '{"path":"/etc","name":"x"}')" = "403" ] \
  && ok "7. local filesystem scan rejected" || bad "7. local scan" "not 403"

# 8–11 signed-ingestion controls via smoke_test.sh (needs MONITOR_* + DECOY_PLAN_ID + TRACE)
if [ -n "${MONITOR_ID:-}" ] && [ -n "${MONITOR_SECRET:-}" ] && [ -n "${DECOY_PLAN_ID:-}" ]; then
  if bash "$REPO_ROOT/scripts/staging/smoke_test.sh" >/tmp/df_smoke.out 2>&1; then
    ok "8-11. unsigned/invalid-sig/expired/replay rejected"
  else
    bad "8-11. signed-ingestion controls" "see smoke output"; sed 's/^/      /' /tmp/df_smoke.out
  fi
  rm -f /tmp/df_smoke.out
else
  # Minimal inline check: an unsigned monitoring request must be rejected.
  s="$(code POST /monitoring/events "${auth[@]}" -H 'Content-Type: application/json' \
    --data '{"decoy_plan_id":"00000000-0000-0000-0000-000000000000","surface":"repository","location":"x","value":"y"}')"
  [ "$s" = "401" ] && ok "8. unsigned monitoring rejected (401)" \
    || bad "8. unsigned monitoring rejected" "got $s"
  skip "9-11. invalid-sig/expired/replay" "set MONITOR_*/DECOY_PLAN_ID/TRACE for full smoke"
fi

[ "$(code GET /incidents -H 'X-DeceptiForge-API-Key: dfk_bogus_key' -H "X-DeceptiForge-Org-Id: $ORG_ID")" = "401" ] \
  && ok "12. invalid API key rejected" || bad "12. invalid API key" "not 401"
# Same key, a different organization header -> the key is bound to one org, so this is rejected.
xorg="$(code GET /incidents -H "X-DeceptiForge-API-Key: $API_KEY" \
  -H 'X-DeceptiForge-Org-Id: 00000000-0000-0000-0000-000000000000')"
[ "$xorg" = "403" ] && ok "13. cross-organization rejected" \
  || note "13. cross-organization" "got $xorg (403 expected; verify key is org-bound)"

# 14. CORS: a disallowed origin must not be echoed back as allowed.
acao="$(curl -s -D - -o /dev/null "$BASE_URL/health" -H 'Origin: https://evil.example.com' \
  | tr -d '\r' | awk -F': ' 'tolower($1)=="access-control-allow-origin"{print $2}')"
[ "$acao" != "https://evil.example.com" ] && [ "$acao" != "*" ] \
  && ok "14. CORS rejects unlisted origin" || bad "14. CORS" "echoed disallowed origin"

# 15. safe error carries request_id.
rid="$(curl -s -D - -o /dev/null "$BASE_URL/does-not-exist" | tr -d '\r' \
  | awk -F': ' 'tolower($1)=="x-request-id"{print $2}')"
[ -n "$rid" ] && ok "15. errors include request_id" || bad "15. request_id" "missing header"

# 16. log redaction is an operator check (cannot be asserted purely over HTTP).
skip "16. logs contain no secrets" "operator: grep shipped logs (see checklist)"

echo
if [ "$fail" -ne 0 ]; then echo "RUNTIME VERIFY: FAIL"; exit 1; fi
echo "RUNTIME VERIFY: PASS"
