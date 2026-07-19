# Purpose: exercise the real psycopg connector adapter against an ephemeral PostgreSQL.
# Responsibilities: on a synthetic schema (never customer data), discover metadata, rank a safe
#   table, generate a schema-valid synthetic row, insert transactionally with read-back, delete only
#   the exact owned row, and prove a modified row blocks deletion (drift). Gated on
#   POSTGRES_TEST_URL, which CI provides; skipped locally.
from __future__ import annotations

import os
from urllib.parse import urlparse

import pytest

from app.services.database.connector_port import ConnectionSpec
from app.services.database.generation import generate_row
from app.services.database.policy import evaluate_table
from app.services.database.psycopg_adapter import PsycopgDatabaseClient
from app.services.database.suitability import score_table

_URL = os.environ.get("POSTGRES_TEST_URL")
pytestmark = pytest.mark.skipif(_URL is None, reason="POSTGRES_TEST_URL not set")

_ALLOWED = ("public",)
_BLOCKED = ("password", "secret", "token", "payment", "outbox")


def _spec() -> ConnectionSpec:
    assert _URL is not None
    parsed = urlparse(_URL.replace("postgresql+psycopg", "postgresql"))
    return ConnectionSpec(
        host=parsed.hostname or "localhost",
        database=(parsed.path or "/").lstrip("/"),
        user=parsed.username or "",
        password=parsed.password or "",
        ssl_mode="disable",  # CI service is on a trusted local network
        connect_timeout_seconds=5,
        statement_timeout_ms=5000,
    )


@pytest.fixture
def synthetic_table():  # type: ignore[no-untyped-def]
    import psycopg

    spec = _spec()
    conn = psycopg.connect(
        host=spec.host, dbname=spec.database, user=spec.user, password=spec.password,
    )
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS public.df_customers")
        cur.execute(
            """
            CREATE TABLE public.df_customers (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                email varchar(255) NOT NULL,
                full_name varchar(120) NOT NULL,
                status varchar(20) NOT NULL DEFAULT 'active'
            )
            """
        )
    yield "df_customers"
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS public.df_customers")
    conn.close()


def test_discover_rank_generate_insert_verify_delete(synthetic_table) -> None:  # type: ignore[no-untyped-def]
    client = PsycopgDatabaseClient()
    spec = _spec()

    snapshot = client.discover_schema(spec, allowed_schemas=_ALLOWED, max_tables=500)
    table = next(t for t in snapshot.tables if t.table_name == "df_customers")

    recommendation = score_table(table, allowed_schemas=_ALLOWED, blocked_patterns=_BLOCKED)
    assert recommendation.deployable

    eligibility = evaluate_table(table, allowed_schemas=_ALLOWED, blocked_patterns=_BLOCKED)
    row = generate_row(table, trace_id="DFH-INT-1", required_fields=eligibility.required_fields)

    result = client.insert_row(
        spec, schema="public", table="df_customers", values=dict(row.values),
        pk_columns=table.primary_key,
    )
    assert result.inserted and result.verified and "id" in result.primary_key

    # Delete only the exact owned row, with an ownership check.
    deleted = client.delete_owned_row(
        spec, schema="public", table="df_customers",
        primary_key=result.primary_key, expected_row=dict(row.values),
    )
    assert deleted.deleted and not deleted.drift


def test_modified_row_blocks_deletion(synthetic_table) -> None:  # type: ignore[no-untyped-def]
    import psycopg

    client = PsycopgDatabaseClient()
    spec = _spec()
    snapshot = client.discover_schema(spec, allowed_schemas=_ALLOWED, max_tables=500)
    table = next(t for t in snapshot.tables if t.table_name == "df_customers")
    eligibility = evaluate_table(table, allowed_schemas=_ALLOWED, blocked_patterns=_BLOCKED)
    row = generate_row(table, trace_id="DFH-INT-2", required_fields=eligibility.required_fields)
    result = client.insert_row(
        spec, schema="public", table="df_customers", values=dict(row.values),
        pk_columns=table.primary_key,
    )

    # Someone changes the row after deployment.
    conn = psycopg.connect(
        host=spec.host, dbname=spec.database, user=spec.user, password=spec.password
    )
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE public.df_customers SET full_name = 'Changed' WHERE id = %s",
            (result.primary_key["id"],),
        )
    conn.close()

    outcome = client.delete_owned_row(
        spec, schema="public", table="df_customers",
        primary_key=result.primary_key, expected_row=dict(row.values),
    )
    assert outcome.drift and not outcome.deleted  # never delete a row that changed
