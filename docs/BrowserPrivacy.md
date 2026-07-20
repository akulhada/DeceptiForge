<!-- Purpose: the browser sensor privacy contract — exactly what is and is not observed, stored,
transmitted, and the limits of client-side secret storage. -->

# Browser sensor privacy

This is the privacy contract for the browser AI-paste sensor. A legal/privacy review is required
before enterprise deployment.

## Principles

- Local matching first; no continuous clipboard monitoring.
- Observe only explicit paste/input events on configured AI domains.
- Never run on unconfigured domains; never capture unrelated browser activity.
- Never inspect password or payment fields.
- Visible status + pause control (when policy allows).
- Bounded, minimized event payloads.

## What the extension stores locally

Sensor id, the scoped signing secret + ingest key, the versioned policy, the compact hashed trace
registry, last-sync metadata, and a bounded queue of already-minimized events. It never stores
pasted text, AI conversation content, model responses, browsing history, or clipboard history.

## What the backend stores per event

Only: browser sensor id, trace id, destination domain + classification, event type, match method,
confidence, extension version, policy version, an optional excerpt **hash**, bounded safe metadata
(e.g. editor kind), correlation id, and the observed timestamp.

The minimizer (`app/services/browser_sensor/minimize.py`) drops any field that could carry raw
content (pasted text, excerpt, selection, clipboard, prompt, output, response, conversation, …) and
bounds field count/length. The ingest API has no raw-content field; such fields are stripped.

## Never stored or logged

Full pasted text, full prompts, full AI responses/conversations, raw embeddings, browsing history,
clipboard history, sensor secrets, or signatures.

## Client-side secret storage limitations

The sensor signing secret and scoped ingest key are held in `chrome.storage.local`, protected by the
browser profile and OS user account. This is **not** a hardware-backed secret store: a user with
full local access to the profile could read it. Mitigations: the key is scoped
(ingest + policy/registry fetch only), revocable and rotatable at any time, and every event is
additionally HMAC-signed and replay-protected. Treat a device compromise as sensor compromise and
revoke.

## Audit

Enrollment, revoke, rotate, policy change, registry sync, event accept/reject, signature failure,
replay rejection, and permission denials are audited (`browser_sensor_audit`). Audit rows never
contain secrets, signatures, pasted text, or conversation content.
