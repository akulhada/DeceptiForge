# Purpose: define the PostgreSQL connector port and adapters (fake + real psycopg).
# Responsibilities: express the least-privilege operations the honey flow needs — connection test,
#   metadata-only schema discovery, transactional single-row insert with read-back verification, and
#   exact-primary-key owned-row deletion. No arbitrary SQL is ever exposed. The fake adapter is
#   deterministic and in-memory; the psycopg adapter enforces TLS/timeouts and only uses
#   statements on approved columns. Dependencies: domain models, psycopg (real adapter only).
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.models.domain.database_honey import (
    ColumnInfo,
    SchemaSnapshot,
    TableInfo,
)

Value = str | int | float | bool | None


@dataclass(frozen=True)
class ConnectionSpec:
    host: str
    database: str
    user: str
    password: str  # resolved in-memory only; never logged or persisted in plaintext
    ssl_mode: str
    connect_timeout_seconds: int
    statement_timeout_ms: int
    application_name: str = "deceptiforge"


@dataclass(frozen=True)
class ConnectionTestResult:
    reachable: bool
    tls_ok: bool
    authenticated: bool
    server_version: str
    read_ok: bool
    write_ok: bool
    statement_timeout_ok: bool
    safe_error_code: str | None = None


@dataclass(frozen=True)
class InsertResult:
    inserted: bool
    primary_key: dict[str, Value]
    verified: bool
    verification_hash: str


@dataclass(frozen=True)
class DeleteResult:
    deleted: bool
    drift: bool  # the stored row no longer matches what we inserted; do not delete


class ConnectorError(Exception):
    """Provider-side failure. Messages are safe (no credentials, no raw rows)."""


class DatabaseConnectorClient(Protocol):
    def test_connection(self, spec: ConnectionSpec) -> ConnectionTestResult: ...

    def discover_schema(
        self, spec: ConnectionSpec, *, allowed_schemas: tuple[str, ...], max_tables: int
    ) -> SchemaSnapshot: ...

    def insert_row(
        self,
        spec: ConnectionSpec,
        *,
        schema: str,
        table: str,
        values: dict[str, Value],
        pk_columns: tuple[str, ...],
    ) -> InsertResult: ...

    def delete_owned_row(
        self,
        spec: ConnectionSpec,
        *,
        schema: str,
        table: str,
        primary_key: dict[str, Value],
        expected_row: dict[str, Value],
    ) -> DeleteResult: ...


def verification_hash(schema: str, table: str, primary_key: dict[str, Value]) -> str:
    parts = ";".join(f"{k}={primary_key[k]!r}" for k in sorted(primary_key))
    canonical = f"{schema}.{table}:{parts}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---- fake adapter --------------------------------------------------------------------------------


@dataclass
class _FakeTable:
    info: TableInfo
    rows: dict[str, dict[str, Value]] = field(default_factory=dict)  # pk-json -> row
    seq: int = 0


class FakeDatabaseClient:
    """Deterministic in-memory PostgreSQL stand-in. No network. Seed with register_table()."""

    def __init__(self, *, server_version: str = "PostgreSQL 16.0") -> None:
        self._tables: dict[tuple[str, str], _FakeTable] = {}
        self._server_version = server_version
        self.fail_write = False

    def register_table(self, table: TableInfo) -> None:
        self._tables[(table.schema_name, table.table_name)] = _FakeTable(info=table)

    def _pk_key(self, pk: dict[str, Value]) -> str:
        return ";".join(f"{k}={pk[k]!r}" for k in sorted(pk))

    def test_connection(self, spec: ConnectionSpec) -> ConnectionTestResult:
        return ConnectionTestResult(
            reachable=True, tls_ok=spec.ssl_mode != "disable", authenticated=True,
            server_version=self._server_version, read_ok=True, write_ok=not self.fail_write,
            statement_timeout_ok=True,
        )

    def discover_schema(
        self, spec: ConnectionSpec, *, allowed_schemas: tuple[str, ...], max_tables: int
    ) -> SchemaSnapshot:
        tables = tuple(
            t.info
            for (schema, _name), t in sorted(self._tables.items())
            if schema in allowed_schemas
        )[:max_tables]
        snap_hash = hashlib.sha256(
            "|".join(f"{t.schema_name}.{t.table_name}" for t in tables).encode()
        ).hexdigest()
        return SchemaSnapshot(
            connector_id="", database_version=self._server_version, tables=tables,
            snapshot_hash=snap_hash,
        )

    def insert_row(
        self, spec: ConnectionSpec, *, schema: str, table: str,
        values: dict[str, Value], pk_columns: tuple[str, ...],
    ) -> InsertResult:
        if self.fail_write:
            raise ConnectorError("write not permitted")
        state = self._tables.get((schema, table))
        if state is None:
            raise ConnectorError("table not found")
        row = dict(values)
        pk: dict[str, Value] = {}
        for col in pk_columns:
            if col in row:
                pk[col] = row[col]
            else:
                state.seq += 1  # database-assigned surrogate key
                pk[col] = state.seq
                row[col] = state.seq
        key = self._pk_key(pk)
        if key in state.rows:
            # Unique/PK collision -> idempotency handled by the caller's fingerprint check.
            raise ConnectorError("duplicate primary key")
        state.rows[key] = row
        return InsertResult(
            inserted=True, primary_key=pk, verified=True,
            verification_hash=verification_hash(schema, table, pk),
        )

    def delete_owned_row(
        self, spec: ConnectionSpec, *, schema: str, table: str,
        primary_key: dict[str, Value], expected_row: dict[str, Value],
    ) -> DeleteResult:
        state = self._tables.get((schema, table))
        if state is None:
            raise ConnectorError("table not found")
        key = self._pk_key(primary_key)
        stored = state.rows.get(key)
        if stored is None:
            return DeleteResult(deleted=False, drift=False)  # already gone
        # Ownership/drift check: every expected value must still match before deleting.
        if any(stored.get(col) != val for col, val in expected_row.items()):
            return DeleteResult(deleted=False, drift=True)
        del state.rows[key]
        return DeleteResult(deleted=True, drift=False)

    # test helpers
    def row_count(self, schema: str, table: str) -> int:
        state = self._tables.get((schema, table))
        return len(state.rows) if state else 0

    def mutate_row(
        self, schema: str, table: str, primary_key: dict[str, Value], **changes: Value
    ) -> None:
        state = self._tables[(schema, table)]
        state.rows[self._pk_key(primary_key)].update(changes)


def _column_from_pg(row: dict[str, Any]) -> ColumnInfo:  # pragma: no cover - real adapter helper
    return ColumnInfo(
        name=row["column_name"],
        data_type=row["data_type"],
        is_nullable=row["is_nullable"] == "YES",
        has_default=row["column_default"] is not None,
        is_generated=row.get("is_generated") == "ALWAYS",
        max_length=row.get("character_maximum_length"),
    )
