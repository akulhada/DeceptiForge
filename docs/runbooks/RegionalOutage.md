<!-- Runbook: primary region outage. -->

# Runbook: regional outage

1. Confirm the outage (readiness failing across primary replicas; provider status).
2. Declare an incident; page the on-call operator + a second approver.
3. Verify the latest backup age (`check_backup_status.sh`) and standby readiness.
4. `failover/request` → separate operator `failover/approve` (fences primary, bumps epoch).
5. Promote the secondary (`promote_secondary.sh`, refuses unless primary fenced).
6. Transfer scheduler leadership; redirect DNS/load balancer.
7. `failover_smoke_test.sh`; confirm exactly one scheduler active and no duplicate side effects.
8. Record achieved RPO/RTO; keep the incident open until failback ([RegionalFailback](../RegionalFailback.md)).
