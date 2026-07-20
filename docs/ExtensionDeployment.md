<!-- Purpose: build, permission, and enterprise-deployment notes for the browser sensor extension. -->

# Extension deployment

The extension lives in `apps/extension` (Plasmo + React + TypeScript, Chromium MV3).

## Build

```bash
pnpm --filter @deceptiforge/extension build   # -> apps/extension/build/chrome-mv3-prod
```

CI runs typecheck, lint, unit tests, a production build, and a hardening audit that fails on any
forbidden permission, on `eval`/`new Function`, on a remote script URL, or on an embedded secret.
The extension is **not** auto-published.

## Manifest permissions (all documented)

- `storage` — sensor state, policy, hashed registry, bounded event queue.
- `alarms` — periodic policy/registry sync and offline retry.
- `host_permissions` / content-script `matches` — the supported AI domains only:
  chatgpt.com, chat.openai.com, claude.ai, gemini.google.com, copilot.microsoft.com, github.com.
- Extension-page CSP: `script-src 'self'; object-src 'self'` — no eval, no remote code.

Deliberately **not** requested: `<all_urls>`, `clipboardRead`, `webRequest`, `history`, broad
`tabs`, `cookies`.

## Security posture

Strict content→background message schema + trusted-sender origin validation (blocks page spoofing).
The signing secret stays in the background service worker. Policies are versioned; a version
regression is rejected (downgrade protection). A minimum extension version can be enforced
(`BROWSER_SENSOR_MIN_EXTENSION_VERSION`). Optionally require signed policies
(`BROWSER_SENSOR_REQUIRE_SIGNED_POLICY`).

## Enterprise deployment options

Distribute via managed Chrome policy (force-install + configured update URL) or the Chrome Web
Store for the organization. Provision each install with a one-time enrollment token; rotate/revoke
per device from the Browser Sensors admin page. Configure the allowed backend domains via
`BROWSER_SENSOR_ALLOWED_DOMAINS`.

## Settings

`BROWSER_SENSOR_ENABLED` (default false), `BROWSER_SENSOR_ENROLLMENT_TTL_SECONDS`,
`BROWSER_SENSOR_EVENT_QUEUE_LIMIT`, `BROWSER_SENSOR_POLICY_SYNC_SECONDS`,
`BROWSER_SENSOR_TRACE_SYNC_SECONDS`, `BROWSER_SENSOR_ALLOWED_DOMAINS`,
`BROWSER_SENSOR_REQUIRE_SIGNED_POLICY`, `BROWSER_SENSOR_MIN_EXTENSION_VERSION`. Explicit
staging/production enablement is required.

## Known limitations

Chromium only this milestone. See [BrowserAiSensor](BrowserAiSensor.md#known-limitations) and the
required legal/privacy review in [BrowserPrivacy](BrowserPrivacy.md).
