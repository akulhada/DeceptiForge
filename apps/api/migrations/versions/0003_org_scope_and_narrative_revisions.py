"""Organization scoping and narrative revisions.

Purpose: add an organization_id boundary to repositories, alerts, and incidents, and replace the
single-per-incident narrative table with an append-only revisions table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_org_scope_narratives"
down_revision = "0002_incident_narratives"
branch_labels = None
depends_on = None

_DEMO_ORG = "00000000-0000-0000-0000-0000000000de"


def upgrade() -> None:
    for table in ("repositories", "alerts", "incidents"):
        op.add_column(
            table,
            sa.Column(
                "organization_id",
                sa.Uuid(),
                nullable=False,
                server_default=_DEMO_ORG,
            ),
        )
        op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])

    op.drop_table("incident_narratives")
    op.create_table(
        "narrative_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("incident_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("context_hash", sa.String(length=64), nullable=False, index=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("narrative_revisions")
    op.create_table(
        "incident_narratives",
        sa.Column("incident_id", sa.Uuid(), primary_key=True),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for table in ("incidents", "alerts", "repositories"):
        op.drop_index(f"ix_{table}_organization_id", table)
        op.drop_column(table, "organization_id")
