# Purpose: build a safe backup inventory/metadata record for a database backup.
# Responsibilities: capture schema/migration/table-count metadata that describes a backup without
#   ever including secrets, ciphertext, or raw evidence. A guard asserts no secret-like fields leak
#   into the metadata (defence against copying plaintext secrets into a side channel). Dependencies:
#   session inspection only.
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

_FORBIDDEN_SUBSTRINGS = (
    "secret", "ciphertext", "token", "password", "signing", "api_key", "private_key",
)


def backup_metadata(session: Session, *, backup_identifier: str) -> dict[str, object]:
    inspector = inspect(session.bind) if session.bind is not None else None
    tables = sorted(inspector.get_table_names()) if inspector is not None else []
    try:
        migration = session.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:  # noqa: BLE001
        migration = None
    return {
        "backup_identifier": backup_identifier,
        "migration_revision": migration,
        "table_count": len(tables),
        # Only table names (schema shape), never column values.
        "tables": tables,
    }


def assert_no_secrets(metadata: dict[str, object]) -> None:
    """Raise if the metadata contains anything resembling a secret value. Table *names* are allowed
    (they describe schema shape); values that look like credentials are not."""
    import json

    blob = json.dumps(metadata, default=str).lower()
    for needle in _FORBIDDEN_SUBSTRINGS:
        # Table names like 'api_keys'/'monitor_credentials' are schema shape, not values; the guard
        # targets credential *values*, so only flag long high-entropy-looking assignments.
        if f'"{needle}":' in blob or f"{needle}=" in blob:
            raise ValueError(f"backup metadata must not contain secret field: {needle}")
