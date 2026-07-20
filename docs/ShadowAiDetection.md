<!-- Purpose: document shadow AI classification, event types, and deterministic alert/incident
mapping for browser paste events. -->

# Shadow AI detection

Destinations are classified against explicit organization policy — never inferred account identity.

## Destination classes

- **approved** — an enterprise/approved AI tenant (e.g. an approved ChatGPT workspace, Claude
  tenant, or Copilot environment).
- **conditional** — conditionally approved AI.
- **shadow** — consumer/personal/unapproved AI tools.
- **unknown** — resembles an AI tool but has no policy entry (treated like shadow for alerting).
- **ignored** — explicitly excluded domains.

Classification is deterministic and longest-match (a tenant subdomain overrides a broader rule). The
extension pre-classifies for display; the **backend re-classifies authoritatively on ingest**. Only
safe domain/tenant metadata is stored — never account identity.

## Event types

`ai_paste_trace_detected`, `shadow_ai_paste_detected`, `approved_ai_paste_detected`,
`repeated_ai_paste`, `multi_tool_ai_exposure`, `extension_policy_violation`,
`browser_sensor_disabled`, `trace_registry_stale`.

## Deterministic exposure + severity

Exposure categories: `ai_paste_leak`, `shadow_ai_exposure`, `approved_ai_policy_violation`,
`repeated_cross_tool_paste`, `multi_surface_ai_exposure`
(`app/services/browser_sensor/classification.py`). Severity starts from the category and is bumped
for repetition, multiple AI tools, and **cross-surface correlation** — when the same trace is also
an active decoy on a RAG/MCP/repository/database surface. GPT never assigns severity.

## False positives

Trace markers are distinctive and events are only trusted from signed sensors, so a stray textual
match is not treated as a paste event on its own. Short/common markers raise false positives; the
reference token is deliberately distinctive.
