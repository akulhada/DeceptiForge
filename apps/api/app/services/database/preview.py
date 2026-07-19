# Purpose: build the exact, deterministic honey-deployment preview before any write.
# Responsibilities: re-evaluate table eligibility, generate the synthetic row, mask values, describe
#   the transaction/verification/delete plan, and compute a stable preview hash. No DB access.
# Dependencies: domain models, policy, generation.
from __future__ import annotations

import hashlib
from datetime import datetime

from app.models.domain.database_honey import (
    GeneratedRow,
    HoneyDecoyType,
    HoneyDeploymentPreview,
    SchemaSnapshot,
    TableInfo,
)
from app.services.database.generation import generate_row
from app.services.database.policy import evaluate_table


class HoneyPreviewError(Exception):
    """Raised when a safe preview cannot be produced (table ineligible)."""


def _mask(value: object) -> str:
    text = str(value)
    if "@" in text:  # email: keep domain, mask local part
        local, _, domain = text.partition("@")
        return f"{local[:2]}…@{domain}"
    if len(text) <= 2:
        return "…"
    return f"{text[:2]}…({len(text)} chars)"


def _find_table(snapshot: SchemaSnapshot, schema: str, table: str) -> TableInfo | None:
    for info in snapshot.tables:
        if info.schema_name == schema and info.table_name == table:
            return info
    return None


def build_preview(
    *,
    deployment_id: str,
    connector_id: str,
    snapshot: SchemaSnapshot,
    schema: str,
    table: str,
    decoy_type: HoneyDecoyType,
    trace_id: str,
    allowed_schemas: tuple[str, ...],
    blocked_patterns: tuple[str, ...],
    expires_at: datetime | None,
) -> tuple[HoneyDeploymentPreview, GeneratedRow]:
    info = _find_table(snapshot, schema, table)
    if info is None:
        raise HoneyPreviewError("table not found in the schema snapshot")
    eligibility = evaluate_table(
        info, allowed_schemas=allowed_schemas, blocked_patterns=blocked_patterns
    )
    if not eligibility.deployable:
        raise HoneyPreviewError("; ".join(eligibility.reasons) or "table not deployable")

    row = generate_row(info, trace_id=trace_id, required_fields=eligibility.required_fields)
    masked = {col: _mask(row.values[col]) for col in row.columns}
    delete_predicate = (
        "DELETE by exact primary key "
        f"({', '.join(info.primary_key) or 'returned key'}) with a full row-value ownership check; "
        "never a broad predicate."
    )
    preview_hash = hashlib.sha256(
        f"{snapshot.snapshot_hash}:{schema}.{table}:{row.row_fingerprint}".encode()
    ).hexdigest()
    preview = HoneyDeploymentPreview(
        deployment_id=deployment_id,
        connector_id=connector_id,
        schema_name=schema,
        table_name=table,
        snapshot_hash=snapshot.snapshot_hash,
        decoy_type=decoy_type,
        columns=row.columns,
        masked_values=masked,
        trace_id=trace_id,
        row_fingerprint=row.row_fingerprint,
        foreign_key_plan=("no required foreign keys (rejected otherwise)",),
        constraint_analysis=(
            f"{len(eligibility.required_fields)} required field(s) generated; "
            "types/nullability/length/enum/UUID-PK satisfied",
        ),
        workflow_trigger_risk=eligibility.risk_flags,
        safety_ok=True,
        warnings=(),
        verification_plan="Insert transactionally, read back the inserted row, verify the primary "
        "key and trace, then commit; monitoring activates only after verification.",
        delete_predicate=delete_predicate,
        expires_at=expires_at,
        expected_monitoring_registration=(trace_id,),
        preview_hash=preview_hash,
    )
    return preview, row
