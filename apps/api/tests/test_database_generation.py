# Purpose: verify column classification, table eligibility policy, safe generation, and suitability.
# Responsibilities: sensitive tables/columns rejected; trigger/FK tables rejected; generated rows
#   satisfy constraints and use only safe synthetic formats (no real PII/payment); suitability never
#   recommends ineligible tables.
from __future__ import annotations

from app.models.domain.database_honey import ColumnInfo, ColumnSensitivity, TableInfo
from app.services.database.classification import classify_column
from app.services.database.generation import generate_row
from app.services.database.policy import evaluate_table
from app.services.database.suitability import score_table

_ALLOWED = ("public",)
_BLOCKED = ("password", "payment", "token", "outbox", "audit")


def _col(name, dtype="varchar", **kw) -> ColumnInfo:  # type: ignore[no-untyped-def]
    return ColumnInfo(name=name, data_type=dtype, is_nullable=kw.pop("nullable", False), **kw)


def _customers() -> TableInfo:
    return TableInfo(
        schema_name="public",
        table_name="customers",
        columns=(
            _col("id", "uuid", is_primary_key=True),
            _col("email", "varchar", max_length=255),
            _col("full_name", "varchar", max_length=120),
            _col("status", "varchar", enum_values=("active", "inactive")),
            _col("balance", "numeric"),
            _col("notes", "text", nullable=True),
        ),
        primary_key=("id",),
    )


# ---- classification ------------------------------------------------------------------------------


def test_classification_flags_sensitive_and_synthetic() -> None:
    assert classify_column("password_hash", "varchar") is ColumnSensitivity.SECRET
    assert classify_column("card_number", "varchar") is ColumnSensitivity.PAYMENT
    assert classify_column("ssn", "varchar") is ColumnSensitivity.REGULATED_IDENTIFIER
    assert classify_column("session_token", "varchar") is ColumnSensitivity.AUTHENTICATION
    assert classify_column("email", "varchar") is ColumnSensitivity.SYNTHETIC_EMAIL
    assert classify_column("created_at", "timestamptz") is ColumnSensitivity.TIMESTAMP


# ---- policy --------------------------------------------------------------------------------------


def test_eligible_business_table_accepted() -> None:
    result = evaluate_table(_customers(), allowed_schemas=_ALLOWED, blocked_patterns=_BLOCKED)
    assert result.deployable
    assert "email" in result.required_fields and "full_name" in result.required_fields
    assert "id" not in result.required_fields  # uuid PK generated, not "required field"


def test_sensitive_column_table_rejected() -> None:
    table = _customers().model_copy(
        update={"columns": (*_customers().columns, _col("password", "varchar"))}
    )
    result = evaluate_table(table, allowed_schemas=_ALLOWED, blocked_patterns=_BLOCKED)
    assert not result.deployable
    assert "password" in result.blocked_fields


def test_trigger_table_rejected() -> None:
    table = _customers().model_copy(update={"has_triggers": True})
    result = evaluate_table(table, allowed_schemas=_ALLOWED, blocked_patterns=_BLOCKED)
    assert not result.deployable
    assert any("trigger" in r for r in result.reasons)


def test_required_foreign_key_table_rejected() -> None:
    table = _customers().model_copy(
        update={
            "columns": (*_customers().columns, _col("org_id", "uuid", is_foreign_key=True)),
            "foreign_keys": ("org_id",),
        }
    )
    result = evaluate_table(table, allowed_schemas=_ALLOWED, blocked_patterns=_BLOCKED)
    assert not result.deployable


def test_blocked_pattern_and_schema_rejected() -> None:
    outbox = _customers().model_copy(update={"table_name": "message_outbox"})
    outbox_result = evaluate_table(outbox, allowed_schemas=_ALLOWED, blocked_patterns=_BLOCKED)
    assert not outbox_result.deployable
    other = _customers().model_copy(update={"schema_name": "internal"})
    assert not evaluate_table(other, allowed_schemas=_ALLOWED, blocked_patterns=_BLOCKED).deployable


# ---- generation ----------------------------------------------------------------------------------


def test_generated_row_is_safe_and_constrained() -> None:
    table = _customers()
    eligibility = evaluate_table(table, allowed_schemas=_ALLOWED, blocked_patterns=_BLOCKED)
    row = generate_row(table, trace_id="DFG-TRACE-1", required_fields=eligibility.required_fields)

    assert row.values["email"].endswith("@example.invalid")  # non-routable domain
    assert "@" in row.values["email"]
    assert row.values["status"] == "active"  # first enum value
    assert row.values["balance"] == 0  # non-payable monetary
    assert isinstance(row.values["id"], str) and len(row.values["id"]) == 36  # uuid PK supplied
    # Length limit respected.
    assert len(row.values["full_name"]) <= 120
    # Trace visibly embedded somewhere.
    assert any("DFGTRACE1" in str(v) or "DFG-TRACE-1" in str(v) for v in row.values.values())
    assert len(row.row_fingerprint) == 64
    # Deterministic.
    again = generate_row(table, trace_id="DFG-TRACE-1", required_fields=eligibility.required_fields)
    assert again.row_fingerprint == row.row_fingerprint


def test_generated_values_never_use_real_payment_or_domains() -> None:
    table = _customers()
    eligibility = evaluate_table(table, allowed_schemas=_ALLOWED, blocked_patterns=_BLOCKED)
    row = generate_row(table, trace_id="t1", required_fields=eligibility.required_fields)
    for value in row.values.values():
        text = str(value)
        assert "@gmail.com" not in text and "@example.com" not in text
        assert not text.isdigit() or len(text) < 12  # no card/routing-length numeric strings


# ---- suitability ---------------------------------------------------------------------------------


def test_suitability_recommends_eligible_rejects_sensitive() -> None:
    rec = score_table(_customers(), allowed_schemas=_ALLOWED, blocked_patterns=_BLOCKED)
    assert rec.deployable and rec.score > 50
    assert rec.recommended_decoy_type.value == "synthetic_customer"

    sensitive = _customers().model_copy(update={"table_name": "user_passwords"})
    bad = score_table(sensitive, allowed_schemas=_ALLOWED, blocked_patterns=("password",))
    assert not bad.deployable and bad.score < 20
