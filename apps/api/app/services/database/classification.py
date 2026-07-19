# Purpose: deterministically classify a database column's sensitivity from its name/type/comment.
# Responsibilities: map columns to a fixed sensitivity taxonomy, erring toward the most restrictive
#   category on ambiguity so unsafe tables are rejected. Pure and deterministic. No DB access.
from __future__ import annotations

from app.models.domain.database_honey import ColumnSensitivity

# Ordered most-restrictive first: the first matching group wins.
_RULES: tuple[tuple[ColumnSensitivity, tuple[str, ...]], ...] = (
    (ColumnSensitivity.SECRET, ("password", "passwd", "pwd", "secret", "private_key", "privkey")),
    (ColumnSensitivity.CREDENTIAL, ("api_key", "apikey", "access_key", "client_secret", "hash")),
    (ColumnSensitivity.AUTHENTICATION, ("token", "session", "auth", "otp", "mfa", "totp")),
    (
        ColumnSensitivity.REGULATED_IDENTIFIER,
        ("ssn", "social_security", "national_id", "passport", "tax_id", "tin", "govt", "license"),
    ),
    (
        ColumnSensitivity.PAYMENT,
        ("card", "cc_num", "pan", "cvv", "cvc", "iban", "routing", "account_number", "bank"),
    ),
    (ColumnSensitivity.HEALTH, ("health", "medical", "diagnosis", "patient", "prescription")),
    (ColumnSensitivity.SYNTHETIC_EMAIL, ("email", "e_mail")),
    (ColumnSensitivity.SYNTHETIC_NAME, ("first_name", "last_name", "full_name", "name")),
    (ColumnSensitivity.MONETARY, ("amount", "price", "total", "balance", "cost", "salary")),
    (
        ColumnSensitivity.REFERENCE_NUMBER,
        ("reference", "ref_no", "invoice", "order_no", "number", "code"),
    ),
    (ColumnSensitivity.STATUS, ("status", "state", "stage")),
    (ColumnSensitivity.FREE_TEXT, ("description", "notes", "comment", "body", "message", "text")),
    (ColumnSensitivity.TIMESTAMP, ("_at", "date", "time", "timestamp", "created", "updated")),
)


def classify_column(
    name: str,
    data_type: str,
    *,
    comment: str | None = None,
    is_foreign_key: bool = False,
    is_primary_key: bool = False,
) -> ColumnSensitivity:
    """Return the deterministic sensitivity for a column."""
    text = f"{name} {comment or ''}".lower()
    for sensitivity, keywords in _RULES:
        if any(keyword in text for keyword in keywords):
            return sensitivity
    if is_foreign_key:
        return ColumnSensitivity.FOREIGN_KEY
    if is_primary_key or name.lower() in {"id", "uuid", "guid"} or name.lower().endswith("_id"):
        return ColumnSensitivity.IDENTIFIER
    if data_type.lower() in {"timestamp", "timestamptz", "date", "time"}:
        return ColumnSensitivity.TIMESTAMP
    if data_type.lower() in {"numeric", "money", "decimal"}:
        return ColumnSensitivity.MONETARY
    return ColumnSensitivity.UNKNOWN
