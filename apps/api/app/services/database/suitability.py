# Purpose: rank a table for honey-record placement and produce a recommendation.
# Responsibilities: score business realism, schema compatibility, operational/workflow risk,
#   monitoring visibility, and rollback feasibility deterministically; never recommend deployment
#   when the table is ineligible or safety confidence is low. Pure. Dependencies: domain, policy,
#   generation.
from __future__ import annotations

from app.models.domain.database_honey import (
    DatabasePlacementRecommendation,
    HoneyDecoyType,
    TableInfo,
)
from app.services.database.generation import _trace_carrier
from app.services.database.policy import TableEligibility, evaluate_table

_DECOY_BY_KEYWORD: tuple[tuple[str, HoneyDecoyType], ...] = (
    ("customer", HoneyDecoyType.CUSTOMER),
    ("client", HoneyDecoyType.CUSTOMER),
    ("invoice", HoneyDecoyType.INVOICE),
    ("subscription", HoneyDecoyType.SUBSCRIPTION),
    ("ticket", HoneyDecoyType.SUPPORT_TICKET),
    ("support", HoneyDecoyType.SUPPORT_TICKET),
    ("order", HoneyDecoyType.ORDER),
    ("account", HoneyDecoyType.ACCOUNT),
    ("transaction", HoneyDecoyType.TRANSACTION),
)


def _decoy_type(table: TableInfo) -> HoneyDecoyType:
    name = table.table_name.lower()
    for keyword, decoy in _DECOY_BY_KEYWORD:
        if keyword in name:
            return decoy
    return HoneyDecoyType.INTERNAL_REFERENCE


def score_table(
    table: TableInfo, *, allowed_schemas: tuple[str, ...], blocked_patterns: tuple[str, ...]
) -> DatabasePlacementRecommendation:
    eligibility: TableEligibility = evaluate_table(
        table, allowed_schemas=allowed_schemas, blocked_patterns=blocked_patterns
    )
    decoy = _decoy_type(table)
    if not eligibility.deployable:
        return DatabasePlacementRecommendation(
            connector_id="",
            schema_name=table.schema_name,
            table_name=table.table_name,
            score=5.0,
            confidence=0.1,
            recommended_decoy_type=decoy,
            required_fields=eligibility.required_fields,
            blocked_fields=eligibility.blocked_fields,
            risk_flags=eligibility.risk_flags,
            reasoning=eligibility.reasons or ("not deployable",),
            deployable=False,
        )

    business = 80.0 if decoy is not HoneyDecoyType.INTERNAL_REFERENCE else 55.0
    monitoring = 90.0 if _trace_carrier(list(table.columns)) else 40.0
    schema_fit = 85.0 if eligibility.required_fields else 60.0
    op_risk = 95.0  # eligible tables already have no triggers / required FKs
    rollback = 90.0  # PK insertable + owned-record deletion
    score = round((business + monitoring + schema_fit + op_risk + rollback) / 5, 1)
    confidence = round(min(monitoring, schema_fit) / 100, 2)
    reasoning = (
        f"eligible {decoy.value} table",
        f"{len(eligibility.required_fields)} required field(s) generatable",
        "trace embeddable" if monitoring > 50 else "limited monitoring visibility",
    )
    return DatabasePlacementRecommendation(
        connector_id="",
        schema_name=table.schema_name,
        table_name=table.table_name,
        score=score,
        confidence=confidence,
        recommended_decoy_type=decoy,
        required_fields=eligibility.required_fields,
        blocked_fields=eligibility.blocked_fields,
        risk_flags=eligibility.risk_flags,
        reasoning=reasoning,
        deployable=True,
    )
