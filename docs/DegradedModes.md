<!-- Purpose: explicit degraded-mode behavior per dependency. -->

# Degraded modes

Computed by `app/services/reliability/degraded.py`; surfaced at `/ready` and
`/admin/reliability/dependencies`.

- **PostgreSQL unavailable** — readiness fails (503); no writes; safe maintenance page; no in-memory
  fallback for durable actions.
- **Redis unavailable** — signed monitoring fails closed where replay protection is mandatory
  (`auth_enabled` + `monitor_signature_required`); safe dashboard reads may continue; durable jobs
  remain in PostgreSQL but paused; health reports degraded.
- **Object storage unavailable** — core alert/incident state continues if no artifact write is
  required; evidence-package generation pauses; artifact-dependent operations fail safely.
- **Secondary integrations unavailable** — deliveries queue in the outbox; core ingestion continues;
  a backlog alert is generated.
- **Maintenance mode** (`MAINTENANCE_MODE=true`) — writes are blocked (`require_writes` fails closed).
