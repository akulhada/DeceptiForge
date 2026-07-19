<!-- Purpose: the safety/threat model for writing synthetic rows into a customer PostgreSQL. -->

# Database deployment safety

Writing into a live customer database is high-risk. Every control below defaults to **reject**.

## Threat model

| Risk | Control |
| --- | --- |
| Writing to a real-affecting table | strict schema allowlist + blocked patterns + sensitivity rejection + trigger/outbox rejection + human approval + bounded transactional INSERT; no UPDATE/DDL/TRUNCATE |
| Generating real PII / payment / credentials | deterministic synthetic-only generation; reserved `example.invalid` domains; no valid card/routing/gov-id; non-payable monetary zeros |
| Credential leakage | connector secrets encrypted at rest (`secret_cipher`), never returned/logged; TLS required outside development |
| Deleting user data on retire/rollback | delete only exact owned primary key with full-row ownership revalidation; `drift_detected` on any change; never broad predicates |
| Cross-organization access | every read/write is organization-scoped |
| Arbitrary SQL | no SQL endpoint; parameterized statements on approved columns only |
| Code execution | metadata-only discovery; no triggers, rules, or stored procedures created |

## Blocked tables

Rejected automatically: tables containing passwords/hashes, auth tokens/sessions, private keys,
payment/bank/card fields, government identifiers, health data; and tables that are outbox/event/CDC,
notification/billing/workflow, ledger/source-of-truth, audit, or queue tables, or that carry
triggers. Configurable via `DATABASE_ALLOWED_SCHEMAS` and `DATABASE_BLOCKED_TABLE_PATTERNS`.

## Foreign keys

First iteration targets tables **without required foreign keys**. Tables that require FKs are
rejected (no real parent rows are ever modified, and broad multi-table deployments are out of scope).

## Transaction and rollback behavior

Insert is a single transaction: insert → read-back → verify PK + trace → commit. Failure before
commit rolls back and registers no monitoring. Retire/rollback run `SELECT … FOR UPDATE` on the
exact primary key, verify the stored row still matches the deployed values, then `DELETE` — or bail
out with `drift_detected` if it changed.

## Limitations (staging)

The live adapter is real (psycopg) but exercised only in CI against an ephemeral database with a
synthetic schema. Do not run against real customer data in staging. No bounded content sampling, no
multi-table dependency chains, no trigger-bearing tables. This is not full production certification.
