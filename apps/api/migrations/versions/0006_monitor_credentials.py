"""Monitor signing credentials.

Purpose: add per-monitor signing credentials whose secret is stored encrypted at rest, used to
verify tamper-evident (HMAC-SHA256) monitoring ingestion requests.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_monitor_credentials"
down_revision = "0005_api_keys_and_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monitor_credentials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("monitor_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("secret_key_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("monitor_id", name="uq_monitor_credential_monitor_id"),
    )


def downgrade() -> None:
    op.drop_table("monitor_credentials")
