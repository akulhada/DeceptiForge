# Purpose: generate a schema-constrained, inert synthetic honey row.
# Responsibilities: satisfy types/nullability/length/enum/UUID-PK while producing only safe
#   synthetic values — reserved non-routable domains, reserved reference prefixes, non-payable
#   monetary values, and never real PII, valid payment identifiers, credentials, or endpoints. Embed
#   trace in a schema-compatible field and compute a deterministic fingerprint. Pure/deterministic.
# Dependencies: domain models, classification, policy.
from __future__ import annotations

import hashlib
import re
from uuid import NAMESPACE_URL, uuid5

from app.models.domain.database_honey import ColumnInfo, ColumnSensitivity, GeneratedRow, TableInfo
from app.services.database.classification import classify_column

_SAFE_DOMAIN = "example.invalid"
_REF_PREFIX = "DFH"
_SYNTHETIC_TIMESTAMP = "2000-01-01 00:00:00+00:00"
_FREE_TEXT = "Synthetic DeceptiForge decoy record. Do not action."

Value = str | int | float | bool | None


class GenerationError(Exception):
    """Raised when a safe synthetic value cannot be produced for a required column."""


def _short(trace_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", trace_id)[:16] or "trace"


def _classified(column: ColumnInfo) -> ColumnSensitivity:
    if column.sensitivity is not ColumnSensitivity.UNKNOWN:
        return column.sensitivity
    return classify_column(
        column.name,
        column.data_type,
        comment=column.comment,
        is_foreign_key=column.is_foreign_key,
        is_primary_key=column.is_primary_key,
    )


def _truncate(value: str, max_length: int | None) -> str:
    return value if max_length is None or len(value) <= max_length else value[:max_length]


def _value_for(column: ColumnInfo, trace_id: str) -> Value:
    sensitivity = _classified(column)
    short = _short(trace_id)
    dtype = column.data_type.lower()
    if column.enum_values:
        return column.enum_values[0]
    if dtype in {"uuid"}:
        return str(uuid5(NAMESPACE_URL, f"{trace_id}:{column.name}"))
    if dtype in {"boolean", "bool"}:
        return False
    _time_types = {"timestamp", "timestamptz", "date", "time"}
    if dtype in _time_types or sensitivity is ColumnSensitivity.TIMESTAMP:
        return _SYNTHETIC_TIMESTAMP
    _money_types = {"numeric", "money", "decimal", "real", "double precision"}
    if dtype in _money_types or sensitivity is ColumnSensitivity.MONETARY:
        return 0  # non-payable, inert
    if dtype in {"integer", "int", "bigint", "smallint"}:
        digest = hashlib.sha256(f"{trace_id}:{column.name}".encode()).hexdigest()[:8]
        return int(digest, 16) % 100000
    if sensitivity is ColumnSensitivity.SYNTHETIC_EMAIL:
        return _truncate(f"decoy.{short}@{_SAFE_DOMAIN}", column.max_length)
    if sensitivity is ColumnSensitivity.SYNTHETIC_NAME:
        return _truncate("Decoy Example", column.max_length)
    if sensitivity is ColumnSensitivity.REFERENCE_NUMBER:
        return _truncate(f"{_REF_PREFIX}-{short}", column.max_length)
    if sensitivity is ColumnSensitivity.STATUS:
        return _truncate("inactive", column.max_length)
    if sensitivity is ColumnSensitivity.FREE_TEXT:
        return _truncate(f"{_FREE_TEXT} trace={short}", column.max_length)
    # Generic safe string.
    return _truncate(f"decoy-{short}", column.max_length)


def _trace_carrier(columns: list[ColumnInfo]) -> str | None:
    """Pick a column that will visibly carry the trace in the row (for export detection)."""
    for wanted in (
        ColumnSensitivity.SYNTHETIC_EMAIL,
        ColumnSensitivity.REFERENCE_NUMBER,
        ColumnSensitivity.FREE_TEXT,
    ):
        for col in columns:
            if _classified(col) is wanted:
                return col.name
    return None


def fingerprint_row(schema: str, table: str, values: dict[str, Value]) -> str:
    canonical = f"{schema}.{table}:" + ";".join(f"{k}={values[k]!r}" for k in sorted(values))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def generate_row(
    table: TableInfo, *, trace_id: str, required_fields: tuple[str, ...]
) -> GeneratedRow:
    """Generate one inert synthetic row covering required fields + UUID primary keys + a trace."""
    by_name = {c.name: c for c in table.columns}
    values: dict[str, Value] = {}

    # UUID primary keys we must supply.
    for pk in table.primary_key:
        col = by_name.get(pk)
        if col is not None and col.data_type.lower() == "uuid" and not (
            col.has_default or col.is_generated
        ):
            values[pk] = _value_for(col, trace_id)

    for name in required_fields:
        col = by_name.get(name)
        if col is None:
            raise GenerationError(f"unknown required column {name}")
        values[name] = _value_for(col, trace_id)

    # Ensure the trace is visibly embedded where the schema allows.
    carrier = _trace_carrier([by_name[n] for n in values if n in by_name] or list(table.columns))
    if carrier and carrier not in values and carrier in by_name:
        values[carrier] = _value_for(by_name[carrier], trace_id)

    fingerprint = fingerprint_row(table.schema_name, table.table_name, values)
    return GeneratedRow(
        trace_id=trace_id,
        columns=tuple(sorted(values)),
        values=values,
        row_fingerprint=fingerprint,
    )
