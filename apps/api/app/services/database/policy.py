# Purpose: decide whether a table may safely receive synthetic honey records.
# Responsibilities: reject tables in disallowed schemas, matching blocked name patterns, containing
#   blocking-sensitivity columns (secrets/credentials/regulated/payment/health/auth), carrying
#   triggers/workflow risk, or requiring foreign keys or non-defaulted non-UUID primary keys. The
#   default is to reject. Pure and deterministic. Dependencies: domain models, classification.
from __future__ import annotations

from dataclasses import dataclass

from app.models.domain.database_honey import (
    BLOCKING_SENSITIVITIES,
    ColumnInfo,
    RiskFlag,
    TableInfo,
)
from app.services.database.classification import classify_column

_UUID_TYPES = frozenset({"uuid"})


@dataclass
class TableEligibility:
    deployable: bool
    reasons: tuple[str, ...] = ()
    risk_flags: tuple[RiskFlag, ...] = ()
    required_fields: tuple[str, ...] = ()
    blocked_fields: tuple[str, ...] = ()


def _classified(column: ColumnInfo) -> ColumnInfo:
    if column.sensitivity is not column.sensitivity.UNKNOWN:
        return column
    return column.model_copy(
        update={
            "sensitivity": classify_column(
                column.name,
                column.data_type,
                comment=column.comment,
                is_foreign_key=column.is_foreign_key,
                is_primary_key=column.is_primary_key,
            )
        }
    )


def _pk_insertable(table: TableInfo, columns: dict[str, ColumnInfo]) -> bool:
    """A PK is insertable when every PK column is a UUID we can generate or has a default/generated
    value the database supplies."""
    for name in table.primary_key:
        col = columns.get(name)
        if col is None:
            return False
        if col.data_type.lower() in _UUID_TYPES:
            continue
        if col.has_default or col.is_generated:
            continue
        return False
    return True


def evaluate_table(
    table: TableInfo, *, allowed_schemas: tuple[str, ...], blocked_patterns: tuple[str, ...]
) -> TableEligibility:
    reasons: list[str] = []
    risks: list[RiskFlag] = []
    blocked_fields: list[str] = []
    columns = {c.name: _classified(c) for c in table.columns}

    if table.schema_name not in allowed_schemas:
        reasons.append(f"schema '{table.schema_name}' is not in the allowlist")

    haystack = f"{table.table_name} {table.comment or ''}".lower()
    for pattern in blocked_patterns:
        if pattern in haystack:
            reasons.append(f"table name/comment matches blocked pattern '{pattern}'")
            break

    for col in columns.values():
        if col.sensitivity in BLOCKING_SENSITIVITIES:
            blocked_fields.append(col.name)
    if blocked_fields:
        reasons.append(f"table has sensitive columns: {', '.join(sorted(set(blocked_fields)))}")

    if table.has_triggers:
        risks.append(RiskFlag(code="triggers", detail="table has triggers"))
        reasons.append("table has triggers (workflow-trigger risk); rejected by default")

    required_fk = [
        c.name
        for c in columns.values()
        if c.is_foreign_key and not c.is_nullable and not c.has_default
    ]
    if required_fk:
        reasons.append(f"table requires foreign keys: {', '.join(required_fk)}")

    if not _pk_insertable(table, columns):
        reasons.append("primary key needs a manual non-UUID value; rejected")

    # Fields we must supply on insert: required (non-null, no default, not generated), excluding PK
    # columns the database will supply and excluding foreign keys.
    required_fields = tuple(
        c.name
        for c in columns.values()
        if not c.is_nullable
        and not c.has_default
        and not c.is_generated
        and not c.is_foreign_key
        and c.name not in table.primary_key
    )

    return TableEligibility(
        deployable=not reasons,
        reasons=tuple(reasons),
        risk_flags=tuple(risks),
        required_fields=required_fields,
        blocked_fields=tuple(sorted(set(blocked_fields))),
    )
