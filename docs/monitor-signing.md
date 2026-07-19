# Signed monitoring ingestion (`monitor-signature-v1`)

Monitoring ingestion can require an HMAC-SHA256 signature so a captured request cannot be replayed
or modified. Enable with `MONITOR_SIGNATURE_REQUIRED=true` (production) once monitor credentials are
provisioned.

## Provisioning a credential

`POST /admin/monitor-credentials` (scope `admin:manage_monitors`) returns the `monitor_id` and the
`signing_secret` **once**. The secret is stored encrypted at rest (never in plaintext) and is never
returned again. Revoke with `DELETE /admin/monitor-credentials/{id}`; credentials may also carry an
`expires_at`.

## Canonical payload

The signing input is UTF-8, newline-separated, version-first:

```
monitor-signature-v1
<HTTP METHOD, uppercased>
<request path, exactly as sent>
<organization id>
<monitor id>
<timestamp>            # unix seconds
<nonce>               # unique per request
<sha256 hex of the exact request body bytes>
```

`signature = HMAC_SHA256(signing_secret, canonical_payload)` as lowercase hex.

## Request headers

| Header | Meaning |
| --- | --- |
| `X-DeceptiForge-Monitor-ID` | credential `monitor_id` |
| `X-DeceptiForge-Timestamp` | unix seconds; must be within the configured skew window |
| `X-DeceptiForge-Nonce` | single-use per organization (replay-protected via Redis) |
| `X-DeceptiForge-Signature` | hex HMAC over the canonical payload |

The organization is taken from the authenticated API key, not from the signature, and cross-org
credential use is rejected. Signatures are compared in constant time. Signatures, secrets, and raw
bodies are never logged.

## Verification order

1. HMAC signature (proves method/path/org/monitor/timestamp/nonce/body are unmodified).
2. Timestamp skew (`MONITORING_TIMESTAMP_SKEW_SECONDS`).
3. Nonce single-use (rejected across all workers via the Redis replay store).
4. Distributed rate limit.

Rejections return a sanitized `detail` and a `request_id`; the failing HTTP status is 401 (invalid
signature / unknown / inactive / expired credential), 403 (cross-organization), 400 (timestamp),
or 409 (replayed nonce).
