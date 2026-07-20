# Service-level objectives

These are targets, not certifications. A staging performance run must record measurements before any
claim of compliance.

| Workload | Target |
| --- | --- |
| Interactive reads | p95 < 500 ms |
| Interactive writes | p95 < 750 ms |
| Monitoring acceptance | p95 < 300 ms, p99 < 1 s, 99.9% success |
| Alert creation | p95 < 5 s from accepted event |
| Incident reconstruction | p95 < 30 s from qualifying alert |
| Dashboard standard tenant data | p95 < 1 s |

Queue wait, execution latency, oldest age, retry rate, and failure rate must be measured per worker
before setting operational alerts.
