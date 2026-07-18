"""Organization scoping across the full pipeline.

Purpose: add organization_id to the remaining pipeline tables and enforce narrative-revision
uniqueness per (organization_id, incident_id, revision_number).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_org_scope_pipeline"
down_revision = "0003_org_scope_and_narrative_revisions"
branch_labels = None
depends_on = None

_DEMO_ORG = "00000000-0000-0000-0000-0000000000de"
_TABLES = (
    "context_profiles",
    "placement_plans",
    "decoy_plans",
    "validation_reports",
    "detection_events",
)


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("organization_id", sa.Uuid(), nullable=False, server_default=_DEMO_ORG),
        )
        op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])
    op.create_unique_constraint(
        "uq_narrative_revision_scope",
        "narrative_revisions",
        ["organization_id", "incident_id", "revision_number"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_narrative_revision_scope", "narrative_revisions", type_="unique")
    for table in _TABLES:
        op.drop_index(f"ix_{table}_organization_id", table)
        op.drop_column(table, "organization_id")
