<!-- Purpose: manual production preflight checklist. -->

# Production preflight checklist

Run against a production-like build (`APP_ENV=production`, `AUTH_ENABLED=true`, `DEMO_ENABLED=false`,
`RATE_LIMIT_MODE=gateway` or `REDIS_URL` set).

1. With `APP_ENV=production` and `DEMO_ENABLED=true`, confirm **no `/demo/*` endpoint exists** (404).
2. Build the web app with `NEXT_PUBLIC_DEMO_MODE=false`; confirm it renders the Connect panel and
   never calls `/demo/*` (see `services/tenantApi.test.ts`).
3. Send ~100 monitoring events with the same trace (valid nonces); verify **one alert** with the
   correct `event_count` and stable `first_seen`.
4. Send the same trace again hours later; verify a **new incident** (episode-scoped id).
5. Run two API workers and exceed monitoring limits; verify the edge/Redis limiter blocks abuse
   (the in-process limiter alone does not coordinate across workers).
6. Submit a monitoring value over `MONITORING_MAX_VALUE_BYTES` (and a chunked body over the proxy
   limit); verify rejection before pipeline work.
7. With a valid key for org A, attempt reads/writes as org B; verify `403`/`404` everywhere.
8. Send malformed UUIDs, oversized locations, invalid surfaces, invalid JSON, non-UTF-8; verify safe
   4xx and a `request_id` in the body.
9. Trigger scans on unreadable dirs / symlink loops / huge repos — only in development; confirm
   production rejects local-path scans.
10. Enable OpenAI with a test key; verify only redacted bounded context is sent and failures fall
    back safely.
11. Confirm the API container runs as non-root (`docker run --rm <image> id` → uid 10001) and does
    not auto-run migrations.
