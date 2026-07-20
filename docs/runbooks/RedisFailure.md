<!-- Runbook: Redis failure. -->

# Runbook: Redis failure

Redis is non-authoritative. On loss:

1. Readiness fails closed where replay protection is mandatory (signed ingestion rejected — safe).
2. No tenant data is lost; durable jobs remain in PostgreSQL; sensor credentials remain durable.
3. Restart/replace Redis; workers reacquire leases safely; duplicate processing stays idempotent.
4. Rate limiting resumes; stale cache never authorizes access.
5. Confirm `/ready` returns ok and replay protection is available again.
