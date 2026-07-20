<!-- Purpose: document the browser AI-paste sensor — enrollment, local matching, minimized signed
reporting, policy/registry sync, revocation, and offline behavior. -->

# Browser AI-paste sensor

A privacy-preserving Chromium extension that detects when DeceptiForge trace markers (or approved
synthetic decoy content) are pasted into AI tools, and reports only minimized, signed evidence.
Disabled by default (`BROWSER_SENSOR_ENABLED`); explicit staging/production enablement required.

## What is observed / not observed

**Observed:** explicit `paste` / `beforeinput(insertFromPaste)` events into eligible editable fields
on **monitored AI domains only**. Matching is local; only a matched trace id, destination domain,
and destination classification leave the page.

**Never observed / captured / stored / transmitted:** pasted text, prompts, AI responses, full
conversations, browsing history, keystrokes, clipboard history, password fields, or payment fields.
No network interception, no `<all_urls>`, no `clipboardRead`, no `webRequest`, no `history`/`tabs`.

## Enrollment

1. An admin creates a one-time, short-lived enrollment token
   (`POST /browser-sensors/enrollment-tokens`, TTL `BROWSER_SENSOR_ENROLLMENT_TTL_SECONDS`).
2. The user enters the token in the extension popup with the backend URL.
3. `POST /browser-sensors/enroll` validates + atomically consumes the token and provisions a sensor
   identity, an encrypted signing secret, and a **separate scoped ingest API key** (`browser_sensor`
   role — never a dashboard key). The secret and key are shown once.
4. The token is invalidated; the extension syncs policy + trace registry.

The signing secret never leaves the background service worker; it is not exposed to page context.
Client-side secret storage limitations are documented in [BrowserPrivacy](BrowserPrivacy.md).

## Local trace matching

The extension holds a compact registry of **irreversible match tokens** (`sha256(trace)`), never
full decoy documents or marker plaintext. On paste it extracts candidate markers (DeceptiForge
tokens, decoy emails), hashes them locally, and compares to the registry. A hit yields only the
trace id. Exact and normalized (case-folded) modes are supported. See
[ShadowAiDetection](ShadowAiDetection.md) for classification, and
[integrations](../docs) trace design in [AiTripwires](AiTripwires.md#trace-design).

## Minimized signed reporting

Detections are sent to `POST /monitoring/browser-events` as `monitor-signature-v1` signed,
replay-protected requests (sensor public id + timestamp + nonce + body hash + HMAC signature). The
backend re-classifies the destination server-side (the extension's guess is not trusted), stores
only minimized metadata, and computes deterministic exposure + severity — GPT never decides
severity. See [BrowserPrivacy](BrowserPrivacy.md) for the exact stored/never-stored fields.

## Policy and registry sync

Central policy (`GET/PUT /browser-ai-policy`) is versioned (monotonic `policy_version`); the
extension rejects a version regression (downgrade protection). The registry
(`GET /browser-trace-registry`) is org-scoped, bounded (`browser_sensor_max_registry_entries`), and
expiry-aware. Sync cadence: `BROWSER_SENSOR_POLICY_SYNC_SECONDS` / `_TRACE_SYNC_SECONDS`.

## Revocation and rotation

`POST /browser-sensors/{id}/revoke` marks the sensor revoked (terminal) and revokes its scoped
ingest key — a revoked sensor can no longer authenticate or report.
`POST /browser-sensors/{id}/rotate` issues a new signing secret (shown once).

## Offline behavior

If the backend is unreachable, only already-minimized events are queued
(`BROWSER_SENSOR_EVENT_QUEUE_LIMIT`), deduped by a stable key so a retry never double-reports, aged
out on expiry, and retried with exponential backoff. Raw content is never queued.

## Permissions rationale

`storage` (sensor state + policy + registry + bounded queue) and `alarms` (periodic sync/retry) only.
Host permissions and content-script matches are scoped to the supported AI domains. See
[ExtensionDeployment](ExtensionDeployment.md).

## Known limitations

Chromium only this milestone (no Firefox/Safari). Some AI surfaces use shadow DOM / custom editors;
detection covers standard paste/beforeinput paths and contenteditable. Paste is never blocked or
mutated (blocking is a future optional policy). A legal/privacy review is required before enterprise
rollout — see [BrowserPrivacy](BrowserPrivacy.md).
