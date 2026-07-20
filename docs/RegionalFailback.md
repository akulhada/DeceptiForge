<!-- Purpose: the controlled manual failback procedure. -->

# Regional failback

Failback is never automatic. `FAILBACK_PENDING` is only reachable from `RECOVERY_VALIDATION`, so the
state machine blocks failback before resynchronization is validated.

## Procedure

1. Stabilize the secondary active region.
2. Repair/rebuild the original region.
3. Resynchronize database + object storage.
4. Validate schema + encrypted data (restore verification).
5. `failback_checklist.sh` (refuses unless `DF_RESYNC_VALIDATED=true`).
6. Fence the current active region at cutover; transfer scheduler leadership.
7. Redirect traffic; validate readiness + side-effect workers.
8. Monitor; close the incident.
