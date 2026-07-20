# Worker scaling

Scale workers from queue depth, oldest job age, drain rate, execution p95, database pool pressure,
and external API budgets—not CPU alone. Reserve capacity for P0/P1 monitoring, alerting, and
reconstruction. Use leases, readiness checks, graceful shutdown, and regional fencing before scaling
side-effect workers.

The reconstruction worker now shares a batch across organizations. Autoscaling policy is operational
configuration; no in-process autoscaler is introduced here.
