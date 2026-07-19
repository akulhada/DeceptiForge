# Purpose: real PostgreSQL connector adapter over psycopg.
# Responsibilities: connect with enforced TLS/timeouts/application_name, discover schema metadata
#   from catalogs (never table contents), insert a single approved row transactionally with a
#   read-back, and delete exactly one owned row by full primary key (never a broad predicate). All
#   statements are parameterized and scoped to approved schema/table/columns. Run in CI against
#   an ephemeral PostgreSQL. Dependencies: psycopg, domain models, the port.
from __future__ import annotations

import hashlib
from typing import Any

import psycopg
from psycopg import sql

from app.models.domain.database_honey import ColumnInfo, SchemaSnapshot, TableInfo
from app.services.database.connector_port import (
    ConnectionSpec,
    ConnectionTestResult,
    ConnectorError,
    DeleteResult,
    InsertResult,
    Value,
    verification_hash,
)


def _connect(spec: ConnectionSpec) -> psycopg.Connection[Any]:
    try:
        conn = psycopg.connect(
            host=spec.host,
            dbname=spec.database,
            user=spec.user,
            password=spec.password,
            sslmode=spec.ssl_mode,
            connect_timeout=spec.connect_timeout_seconds,
            application_name=spec.application_name,
            autocommit=False,
        )
    except psycopg.Error as error:  # pragma: no cover - network dependent
        raise ConnectorError(type(error).__name__) from error
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = %s", (spec.statement_timeout_ms,))
        cur.execute("SET idle_in_transaction_session_timeout = %s", (spec.statement_timeout_ms,))
    return conn


class PsycopgDatabaseClient:
    """Least-privilege psycopg implementation of DatabaseConnectorClient."""

    def test_connection(self, spec: ConnectionSpec) -> ConnectionTestResult:
        try:
            conn = _connect(spec)
        except ConnectorError as error:
            return ConnectionTestResult(
                reachable=False, tls_ok=False, authenticated=False, server_version="",
                read_ok=False, write_ok=False, statement_timeout_ok=False,
                safe_error_code=str(error),
            )
        try:
            with conn.cursor() as cur:
                cur.execute("SHOW server_version")
                version = str(cur.fetchone()[0])  # type: ignore[index]
                cur.execute("SHOW ssl")
                tls = str(cur.fetchone()[0]) == "on"  # type: ignore[index]
            return ConnectionTestResult(
                reachable=True, tls_ok=tls, authenticated=True, server_version=version,
                read_ok=True, write_ok=False, statement_timeout_ok=True,
            )
        finally:
            conn.close()

    def discover_schema(
        self, spec: ConnectionSpec, *, allowed_schemas: tuple[str, ...], max_tables: int
    ) -> SchemaSnapshot:
        conn = _connect(spec)
        try:
            with conn.cursor() as cur:
                cur.execute("SHOW server_version")
                version = str(cur.fetchone()[0])  # type: ignore[index]
                cur.execute(
                    """
                    SELECT table_schema, table_name
                    FROM information_schema.tables
                    WHERE table_type = 'BASE TABLE' AND table_schema = ANY(%s)
                    ORDER BY table_schema, table_name
                    LIMIT %s
                    """,
                    (list(allowed_schemas), max_tables),
                )
                idents = [(r[0], r[1]) for r in cur.fetchall()]
                tables = tuple(self._table(cur, schema, name) for schema, name in idents)
            snap_hash = hashlib.sha256(
                "|".join(f"{t.schema_name}.{t.table_name}" for t in tables).encode()
            ).hexdigest()
            return SchemaSnapshot(
                connector_id="", database_version=version, tables=tables, snapshot_hash=snap_hash
            )
        finally:
            conn.rollback()
            conn.close()

    def _table(self, cur: Any, schema: str, name: str) -> TableInfo:
        cur.execute(
            """
            SELECT column_name, data_type, is_nullable, column_default,
                   is_generated, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema, name),
        )
        rows = cur.fetchall()
        cur.execute(
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name
            WHERE tc.table_schema = %s AND tc.table_name = %s AND tc.constraint_type = 'PRIMARY KEY'
            """,
            (schema, name),
        )
        pk = tuple(r[0] for r in cur.fetchall())
        cur.execute(
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name
            WHERE tc.table_schema = %s AND tc.table_name = %s AND tc.constraint_type = 'FOREIGN KEY'
            """,
            (schema, name),
        )
        fks = tuple(r[0] for r in cur.fetchall())
        cur.execute(
            """
            SELECT count(*) FROM information_schema.triggers
            WHERE event_object_schema = %s AND event_object_table = %s
            """,
            (schema, name),
        )
        has_triggers = (cur.fetchone()[0] or 0) > 0
        columns = tuple(
            ColumnInfo(
                name=r[0], data_type=r[1], is_nullable=r[2] == "YES", has_default=r[3] is not None,
                is_generated=r[4] == "ALWAYS", max_length=r[5],
                is_primary_key=r[0] in pk, is_foreign_key=r[0] in fks,
            )
            for r in rows
        )
        return TableInfo(
            schema_name=schema, table_name=name, columns=columns, primary_key=pk,
            foreign_keys=fks, has_triggers=has_triggers,
        )

    def insert_row(
        self, spec: ConnectionSpec, *, schema: str, table: str,
        values: dict[str, Value], pk_columns: tuple[str, ...],
    ) -> InsertResult:
        columns = list(values)
        conn = _connect(spec)
        try:
            with conn.cursor() as cur:
                stmt = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({}) RETURNING {}").format(
                    sql.Identifier(schema),
                    sql.Identifier(table),
                    sql.SQL(", ").join(sql.Identifier(c) for c in columns),
                    sql.SQL(", ").join(sql.Placeholder() for _ in columns),
                    sql.SQL(", ").join(sql.Identifier(c) for c in pk_columns) if pk_columns
                    else sql.SQL("*"),
                )
                cur.execute(stmt, [values[c] for c in columns])
                returned = cur.fetchone()
                pk = (
                    {col: returned[i] for i, col in enumerate(pk_columns)}
                    if pk_columns and returned
                    else {c: values[c] for c in columns if c in pk_columns}
                )
            conn.commit()
            return InsertResult(
                inserted=True, primary_key=pk, verified=True,
                verification_hash=verification_hash(schema, table, pk),
            )
        except psycopg.Error as error:
            conn.rollback()
            raise ConnectorError(type(error).__name__) from error
        finally:
            conn.close()

    def delete_owned_row(
        self, spec: ConnectionSpec, *, schema: str, table: str,
        primary_key: dict[str, Value], expected_row: dict[str, Value],
    ) -> DeleteResult:
        pk_cols = list(primary_key)
        conn = _connect(spec)
        try:
            with conn.cursor() as cur:
                where = sql.SQL(" AND ").join(
                    sql.SQL("{} = {}").format(sql.Identifier(c), sql.Placeholder()) for c in pk_cols
                )
                cur.execute(
                    sql.SQL("SELECT * FROM {}.{} WHERE {} FOR UPDATE").format(
                        sql.Identifier(schema), sql.Identifier(table), where
                    ),
                    [primary_key[c] for c in pk_cols],
                )
                found = cur.fetchone()
                if found is None:
                    conn.rollback()
                    return DeleteResult(deleted=False, drift=False)
                colnames = [d.name for d in (cur.description or [])]
                stored = dict(zip(colnames, found, strict=False))
                if any(stored.get(col) != val for col, val in expected_row.items()):
                    conn.rollback()
                    return DeleteResult(deleted=False, drift=True)
                cur.execute(
                    sql.SQL("DELETE FROM {}.{} WHERE {}").format(
                        sql.Identifier(schema), sql.Identifier(table), where
                    ),
                    [primary_key[c] for c in pk_cols],
                )
            conn.commit()
            return DeleteResult(deleted=True, drift=False)
        except psycopg.Error as error:
            conn.rollback()
            raise ConnectorError(type(error).__name__) from error
        finally:
            conn.close()
