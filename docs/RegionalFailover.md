<!-- Purpose: the controlled regional failover state machine + procedure. -->

# Regional failover

Failover states (`FailoverState`): normal → degraded → failover_requested → primary_fenced →
standby_promoting → secondary_active → recovery_validation → failback_pending → normal_restored.

## Procedure

1. Declare an incident.
2. `POST /admin/reliability/failover/request` (scope `failover:request`).
3. A **different** operator approves (`failover:approve`) — separation of duties enforced; approval
   fences the primary (`fence_primary.sh`, bumps `ACTIVE_REGION_EPOCH`).
4. Promote the secondary only after fencing is confirmed (`promote_secondary.sh` refuses otherwise).
5. Transfer scheduler leadership (set the new region `CLUSTER_ROLE=primary`, `SCHEDULERS_ENABLED=true`).
6. Update DNS/load-balancer; validate readiness (`failover_smoke_test.sh`).
7. Every transition is audited (`failover_events`).

Do not promote a secondary while the primary may still accept writes. No automatic failover.
