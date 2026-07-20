# Staging performance certification

1. Capture idle baseline, pool utilization, and critical query plans.
2. Run expected medium-tenant mixed traffic and evaluate SLO targets.
3. Run 10x monitoring burst and sensor reconnect storm; verify bounded 429s and queue recovery.
4. Restart Redis/workers, simulate SIEM outage and database pressure, and verify idempotency.
5. Run a large noisy neighbor beside a small tenant; the small tenant must retain its SLO.
6. Persist a performance report with methodology version, code revision, topology, synthetic workload,
   percentiles, utilization, SLO result, bottlenecks, and remediation.

Do not run destructive scale tests in production or shared developer environments.
