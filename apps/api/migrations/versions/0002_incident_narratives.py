"""Incident narrative table.

Purpose: persist optional GPT/fallback incident narratives beside deterministic incidents,
keyed by incident id so a narrative never overwrites reconstruction output.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_incident_narratives"
down_revision = "0001_pipeline_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incident_narratives",
        sa.Column("incident_id", sa.Uuid(), primary_key=True),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("incident_narratives")
