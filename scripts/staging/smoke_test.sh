#!/usr/bin/env bash
# Purpose: end-to-end signed-ingestion smoke test against a running staging API.
# Behavior: builds a monitor-signature-v1 request, submits one monitoring event, and proves both the
#   happy path (valid signed ingest against a seeded decoy plan returns 200) and the security controls
#   — replay rejection, body-tamper rejection, expired-timestamp rejection. A missing/unseeded decoy
#   plan fails the test (no false pass on the 409 that also signals replay). Never logs the monitor
#   secret or the full signature.
#
# Required environment:
#   BASE_URL          e.g. https://staging.example.com
#   API_KEY           API key with monitoring:ingest scope
#   ORG_ID            organization UUID bound to the API key
#   MONITOR_ID        monitor credential id (dfm_...)
#   MONITOR_SECRET    monitor signing secret (never logged)
#   DECOY_PLAN_ID     a seeded decoy plan UUID
#   TRACE             the decoy trace identifier present in the plan
set -euo pipefail

for v in BASE_URL API_KEY ORG_ID MONITOR_ID MONITOR_SECRET DECOY_PLAN_ID TRACE; do
  [ -n "${!v:-}" ] || { echo "smoke: missing required env $v"; exit 2; }
done

PATH_INGEST="/monitoring/events"
fail=0
note() { printf '  %-40s %s\n' "$1" "$2"; }
check() { if [ "$2" = "$3" ]; then note "$1" "ok ($2)"; else note "$1" "FAIL (want $3, got $2)"; fail=1; fi; }

sha256hex() { printf '%s' "$1" | openssl dgst -sha256 | awk '{print $NF}'; }
hmac_sig() { printf '%s' "$1" | openssl dgst -sha256 -hmac "$MONITOR_SECRET" | awk '{print $NF}'; }

# Post a signed request; echoes the HTTP status. Secret/signature are never printed.
post_signed() {
  local body="$1" ts="$2" nonce="$3" send_body="${4:-$1}"
  local body_hash canonical sig
  body_hash="$(sha256hex "$body")"
  canonical="$(printf 'monitor-signature-v1\nPOST\n%s\n%s\n%s\n%s\n%s\n%s' \
    "$PATH_INGEST" "$ORG_ID" "$MONITOR_ID" "$ts" "$nonce" "$body_hash")"
  sig="$(hmac_sig "$canonical")"
  curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE_URL$PATH_INGEST" \
    -H 'Content-Type: application/json' \
    -H "X-DeceptiForge-API-Key: $API_KEY" \
    -H "X-DeceptiForge-Org-Id: $ORG_ID" \
    -H "X-DeceptiForge-Monitor-ID: $MONITOR_ID" \
    -H "X-DeceptiForge-Timestamp: $ts" \
    -H "X-DeceptiForge-Nonce: $nonce" \
    -H "X-DeceptiForge-Signature: $sig" \
    --data-binary "$send_body"
}

BODY="$(printf '{"decoy_plan_id":"%s","surface":"repository","location":"src/x.py","value":"copied %s"}' \
  "$DECOY_PLAN_ID" "$TRACE")"
NOW="$(date +%s)"
NONCE="smoke-$(date +%s%N)"

echo "== signed ingestion smoke =="

# 1) Valid signed request. MUST be 200 (signature accepted AND the seeded decoy plan matched, so an
#    alert is created). A 409 here means the decoy plan was not seeded (DECOY_PLAN_ID/TRACE do not
#    resolve to a real plan) — the happy path was never exercised, so the smoke test must FAIL rather
#    than pass on a missing-plan 409 (which is also the replay-rejection code, hiding a false pass).
status="$(post_signed "$BODY" "$NOW" "$NONCE")"
if [ "$status" = "200" ]; then note "valid ingest" "ok (200, alert created)";
elif [ "$status" = "409" ]; then
  note "valid ingest" "FAIL (409: decoy plan not seeded — seed DECOY_PLAN_ID/TRACE before smoke)"; fail=1;
else note "valid ingest" "FAIL (got $status, want 200)"; fail=1; fi

# 2) Replay the exact same request (same nonce) -> 409 replayed nonce.
check "replayed nonce rejected" "$(post_signed "$BODY" "$NOW" "$NONCE")" "409"

# 3) Reuse the signature but change the body -> 401 invalid signature.
TAMPERED="$(printf '{"decoy_plan_id":"%s","surface":"repository","location":"src/x.py","value":"tampered"}' \
  "$DECOY_PLAN_ID")"
# Sign the original body, send the tampered body (body hash no longer matches).
note_status="$(
  body_hash="$(sha256hex "$BODY")"
  canonical="$(printf 'monitor-signature-v1\nPOST\n%s\n%s\n%s\n%s\n%s\n%s' \
    "$PATH_INGEST" "$ORG_ID" "$MONITOR_ID" "$NOW" "tamper-$NONCE" "$body_hash")"
  sig="$(hmac_sig "$canonical")"
  curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE_URL$PATH_INGEST" \
    -H 'Content-Type: application/json' -H "X-DeceptiForge-API-Key: $API_KEY" \
    -H "X-DeceptiForge-Org-Id: $ORG_ID" -H "X-DeceptiForge-Monitor-ID: $MONITOR_ID" \
    -H "X-DeceptiForge-Timestamp: $NOW" -H "X-DeceptiForge-Nonce: tamper-$NONCE" \
    -H "X-DeceptiForge-Signature: $sig" --data-binary "$TAMPERED"
)"
check "body tamper rejected" "$note_status" "401"

# 4) Expired timestamp -> 400 outside clock skew.
check "expired timestamp rejected" "$(post_signed "$BODY" "1" "expired-$NONCE")" "400"

echo
if [ "$fail" -ne 0 ]; then echo "SMOKE: FAIL"; exit 1; fi
echo "SMOKE: PASS (alerts/incidents appear after the reconstruction worker runs; verify via the dashboard)"
