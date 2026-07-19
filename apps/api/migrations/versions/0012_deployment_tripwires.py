"""Deployment tripwire activations.

Purpose: persist monitoring/tripwire activations that are created only after a verified merge, so
activation is durable, idempotent (unique per deployment + trace), and reversible on retire/rollback.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_deployment_tripwires"
down_revision = "0011_decoy_deployments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deployment_tripwires",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("deployment_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("decoy_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("trace_identifier", sa.String(length=128), nullable=False, index=True),
        sa.Column("target_path", sa.String(length=2048), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("deployment_id", "trace_identifier", name="uq_deployment_tripwire"),
    )


def downgrade() -> None:
    op.drop_table("deployment_tripwires")
