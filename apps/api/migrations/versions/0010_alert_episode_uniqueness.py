"""Alert episode uniqueness and event count.

Purpose: add the per-episode uniqueness identity (organization, deduplication key, time bucket) and
an event_count column so alert upserts are atomic at the database boundary and concurrent duplicate
ingests cannot create duplicate alert rows.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_alert_episode_uniqueness"
down_revision = "0009_retention_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alerts",
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column("alerts", sa.Column("episode_bucket", sa.BigInteger(), nullable=True))
    op.create_unique_constraint(
        "uq_alert_episode",
        "alerts",
        ["organization_id", "deduplication_key", "episode_bucket"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_alert_episode", "alerts", type_="unique")
    op.drop_column("alerts", "episode_bucket")
    op.drop_column("alerts", "event_count")
