"""Async incident reconstruction: indexed alert correlation columns and a work queue.

Purpose: promote strong correlation keys on alerts to indexed columns and add a reconstruction
work table so monitoring ingestion can enqueue reconstruction instead of running it synchronously.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_reconstruction_queue"
down_revision = "0006_monitor_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alerts", sa.Column("affected_placement_id", sa.Uuid(), nullable=True))
    op.add_column("alerts", sa.Column("correlation_id", sa.Uuid(), nullable=True))
    op.add_column("alerts", sa.Column("deduplication_key", sa.String(length=512), nullable=True))
    op.add_column("alerts", sa.Column("first_seen", sa.DateTime(timezone=True), nullable=True))
    op.add_column("alerts", sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_alerts_affected_placement_id", "alerts", ["affected_placement_id"])
    op.create_index("ix_alerts_correlation_id", "alerts", ["correlation_id"])
    op.create_index("ix_alerts_deduplication_key", "alerts", ["deduplication_key"])
    op.create_index("ix_alerts_first_seen", "alerts", ["first_seen"])
    op.create_index("ix_alerts_last_seen", "alerts", ["last_seen"])

    op.create_table(
        "reconstruction_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("trace_identifier", sa.String(length=128), nullable=False),
        sa.Column("decoy_id", sa.Uuid(), nullable=False),
        sa.Column("affected_placement_id", sa.Uuid(), nullable=True),
        sa.Column("correlation_id", sa.Uuid(), nullable=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_reconstruction_jobs_status", "reconstruction_jobs", ["status"])
    op.create_index("ix_reconstruction_jobs_created_at", "reconstruction_jobs", ["created_at"])


def downgrade() -> None:
    op.drop_table("reconstruction_jobs")
    for name in (
        "ix_alerts_last_seen",
        "ix_alerts_first_seen",
        "ix_alerts_deduplication_key",
        "ix_alerts_correlation_id",
        "ix_alerts_affected_placement_id",
    ):
        op.drop_index(name, table_name="alerts")
    for column in (
        "last_seen",
        "first_seen",
        "deduplication_key",
        "correlation_id",
        "affected_placement_id",
    ):
        op.drop_column("alerts", column)
