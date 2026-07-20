<!-- Purpose: define safe, deterministic monitoring activation for accepted decoys. -->

# Monitoring Instrumentation

Monitoring Instrumentation consumes generated assets and Believability/Safety reports. Only reports with `decision = accept` are registered; warn and reject reports produce no active tripwire. Registration is in-memory metadata only: it never writes target files, inserts database data, calls an external service, or enables a network callback.

The MVP supports caller-provided file content, repository files, database/export payloads, and generic text/paste payloads. Each registry entry maps a trace identifier to a decoy, placement, target location, and template. Exact trace matches emit confidence `1.0`; separator-normalized matches emit `0.85`. The event includes a capped 256-character excerpt and SHA-256 payload digest, never the full payload. Duplicate trace/location/content observations are suppressed.

The registration plan and health metadata expose active in-process monitor types. The browser AI-paste, database listener, RAG, MCP, and agent-session adapters are implemented (each disabled by default behind its own feature flag); they call the same text-scan boundary and send accepted, minimized, signed events to the alerting pipeline and incident reconstruction. Matching is O(T × P) for active trace count T and payload length P; it intentionally avoids fuzzy matching.
