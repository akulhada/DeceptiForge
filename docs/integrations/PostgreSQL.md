<!-- Purpose: document the PostgreSQL connector — least-privilege roles, TLS, discovery, and the
adapter status. -->

# PostgreSQL connector

DeceptiForge connects to an organization's PostgreSQL to discover suitable tables and deploy
synthetic honey records. Disabled by default (`DATABASE_CONNECTORS_ENABLED`,
`DATABASE_HONEY_DEPLOYMENT_ENABLED`). No arbitrary-SQL endpoint exists; all statements are
parameterized and scoped to approved schema/table/columns.

## Least-privilege roles (recommended)

Create dedicated roles — never superuser, no role creation, no schema ownership, no extensions.

```sql
-- Discovery + schema metadata (and SELECT only on approved tables if needed).
CREATE ROLE deceptiforge_reader LOGIN PASSWORD '…';
GRANT USAGE ON SCHEMA public TO deceptiforge_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO deceptiforge_reader;   -- optional, for verification

-- Writer: INSERT/DELETE only on specifically approved tables. No UPDATE, no DDL, no TRUNCATE,
-- no trigger management.
CREATE ROLE deceptiforge_writer LOGIN PASSWORD '…';
GRANT USAGE ON SCHEMA public TO deceptiforge_writer;
GRANT INSERT, DELETE, SELECT ON public.<approved_table> TO deceptiforge_writer;
```

## Connection security (enforced by the adapter)

- **TLS** required outside development (`DATABASE_REQUIRE_TLS=true`; `sslmode=require` or stronger).
- Connection timeout (`DATABASE_CONNECT_TIMEOUT_SECONDS`), statement timeout and idle-in-transaction
  timeout (`DATABASE_STATEMENT_TIMEOUT_MS`), and `application_name=deceptiforge`.
- No superuser credentials; no role creation, schema ownership, extension install, or trusted
  `search_path`.

## Discovery

Schema is read from `information_schema` / catalogs (schemas, tables, columns, types, nullability,
PK/unique/FK/check, indexes, generated/default columns, estimated rows, comments, triggers). Table
**contents are not read** by default. Bounded, redacted, read-only sampling is out of scope for this
milestone.

## Credentials

Connector credentials are accepted once, encrypted at rest via the evidence encryption boundary
(`secret_cipher`), and **never returned or logged**. Production must not store plaintext connector
secrets. Prefer a secret-manager reference.

## Adapter status

`RepositoryDeploymentClient`'s database analogue is `DatabaseConnectorClient`
(`app/services/database/connector_port.py`). Two adapters:

- `FakeDatabaseClient` — deterministic, in-memory, network/token-free (development + unit tests).
- `PsycopgDatabaseClient` — the real adapter (TLS/timeouts, parameterized insert, exact-PK
  `FOR UPDATE` delete with a full-row ownership check). Exercised in CI against an ephemeral
  PostgreSQL with a synthetic schema (`tests/test_database_honey_integration.py`), never customer
  data.

The deployment worker (`python -m app.jobs.database_honey`) runs off the API path and is gated on the
feature flag.
