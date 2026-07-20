<!-- Purpose: generic signed webhook signature verification + SSRF controls. -->

# Webhook signature verification + SSRF controls

## Signature

Generic webhook deliveries are HMAC-SHA256 signed. Headers:

- `X-DeceptiForge-Delivery-ID`
- `X-DeceptiForge-Timestamp`
- `X-DeceptiForge-Signature`
- `X-DeceptiForge-Event`
- `X-DeceptiForge-Schema-Version`

The signed canonical string is newline-joined:

```
df-webhook-v1
<delivery id>
<event type>
<timestamp>
<sha256(body)>
```

Receiver verification:

1. Recompute `sha256(raw_body)`.
2. Rebuild the canonical string from the headers + body hash.
3. `HMAC-SHA256(shared_secret, canonical)` and constant-time compare to `X-DeceptiForge-Signature`.
4. Reject if the timestamp is outside your allowed skew (replay resistance).

The shared secret is the integration's stored (encrypted) signing secret. It is never transmitted.

## SSRF controls

Endpoints are validated at create and again before every delivery
(`app/services/integrations/ssrf.py`):

- scheme must be https (http only in development); no credentials embedded in the URL;
- per-organization domain allowlist (`SECURITY_EXPORT_ALLOWED_DOMAINS`);
- DNS is resolved and **every** resolved address is checked; loopback, link-local, private,
  reserved, and cloud-metadata (`169.254.169.254`, `metadata.google.internal`, …) destinations are
  rejected;
- private networks are only reachable when `SECURITY_EXPORT_ALLOW_PRIVATE_NETWORKS=true` in
  development;
- the HTTP transport disables redirects (an open redirect could bypass validation), sets a strict
  timeout, and caps the response snippet.
