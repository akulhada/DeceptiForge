<!-- Purpose: document the database honey-record lifecycle: discovery, generation, approval,
transactional insertion, monitoring, and retire/rollback/rotate. -->

# Database honey records

Deploy believable **synthetic** rows into approved business tables as tripwires, then monitor,
expire, retire, and roll them back without touching real data.

Supported decoy types: synthetic customer, invoice, subscription, support ticket, order, account,
clearly-inert transaction, and internal reference rows. Not supported: schema changes, triggers,
stored procedures, arbitrary SQL, real payment/bank/card data, real credentials, or regulated PII.

## Flow

```
register connector -> test -> sync-schema -> rank tables -> create deployment (+ preview)
  -> submit -> approve -> deploy -> [worker: insert + verify + activate monitoring]
deployed -> retire / rollback (delete only the exact owned row) ; drift -> drift_detected (manual)
```

The state machine (`app/models/domain/database_honey.py`) rejects illegal transitions (409).
Permissions: `database_connectors:{read,manage}`, `database_schema:read`,
`database_honey:{read,create,approve,deploy,retire,rollback}`. Separation of duties
(`REQUIRE_SEPARATE_DATABASE_APPROVER`) prevents the requester from approving their own deployment.

## Table suitability

Tables are ranked deterministically. A table is **rejected** when it is in a disallowed schema,
matches a blocked name pattern, contains blocking-sensitivity columns
(secrets/credentials/regulated/payment/health/auth), has triggers (workflow-trigger risk), requires
foreign keys, or has a non-defaulted non-UUID primary key. See `docs/DatabaseDeploymentSafety.md`.

## Generation (safe synthetic data)

The row satisfies types/nullability/length/enum and supplies UUID primary keys. Values are inert:
reserved non-routable email domains (`example.invalid`), reserved reference prefixes (`DFH-`),
non-payable monetary zeros — never real phone numbers, valid cards, bank routing/account numbers,
government identifiers, or real identities. The trace is embedded in a schema-compatible field. GPT
is not used for these rows.

## Insertion, verification, and monitoring activation

The worker regenerates the exact row deterministically (the preview stores only masked values),
re-runs safety, opens a TLS connection with strict timeouts, and in one transaction inserts the row,
reads it back, and verifies the primary key + trace before committing. **Monitoring activates only
after verification.** If insertion fails before commit, the transaction is rolled back and no
monitoring is registered. If activation fails after commit, the deployment is marked
`deployed_unmonitored`, a high-priority `database_honey_activation_failed` metric is emitted, and
rollback/retirement is offered — success is never silently claimed.

Insertion is idempotent: a deterministic row fingerprint (unique per deployment) means a retried job
never inserts a duplicate row.

## Monitoring

External monitoring events reference deployed honey records by organization, connector, deployment,
table, record, trace, and monitor identity (e.g. a trace value seen in an export, the honey key
queried through a trusted sensor). Invasive database triggers are not used in this milestone.

## Retirement, rollback, rotation, expiry

Retirement and rollback delete **only the exact owned row**, matched by full primary key with a
full-row ownership revalidation — never a broad predicate (email prefix, timestamp range, status).
If the row changed unexpectedly, the deployment is marked `drift_detected` and nothing is deleted
until a human reviews it. Rotation retires the current row and links a replacement deployment,
preserving incident history. Each deployment carries `expires_at` (`DATABASE_DEFAULT_EXPIRY_DAYS`).

## Incident response — failed activation

`deployed_unmonitored` means the row is live but untripwired. Investigate the registry, then re-run
activation or roll back. Do not treat it as a successful deployment.
