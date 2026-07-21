"""judge sandbox sessions

Adds the TTL-bound sandbox session table backing the restricted judge workspace. Each session owns
a generated organization id so judge-created records never share a namespace with a tenant or with
another judge.

Revision ID: 0023_judge_sandboxes
Revises: 0022_learning
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023_judge_sandboxes"
down_revision = "0022_learning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "judge_sandboxes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        # Unique: an organization id belongs to exactly one sandbox session, which is what makes it
        # usable as an isolation boundary.
        sa.Column("organization_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("session_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("api_key_id", sa.Uuid(), nullable=True),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("analysis_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("interactions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exports", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resets", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_judge_sandboxes_organization_id", "judge_sandboxes", ["organization_id"])
    op.create_index("ix_judge_sandboxes_session_id", "judge_sandboxes", ["session_id"])
    op.create_index("ix_judge_sandboxes_status", "judge_sandboxes", ["status"])
    # Expiry sweeps scan by deadline.
    op.create_index("ix_judge_sandboxes_expires_at", "judge_sandboxes", ["expires_at"])
    op.create_index(
        "ix_judge_sandboxes_org_session", "judge_sandboxes", ["organization_id", "session_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_judge_sandboxes_org_session", table_name="judge_sandboxes")
    op.drop_index("ix_judge_sandboxes_expires_at", table_name="judge_sandboxes")
    op.drop_index("ix_judge_sandboxes_status", table_name="judge_sandboxes")
    op.drop_index("ix_judge_sandboxes_session_id", table_name="judge_sandboxes")
    op.drop_index("ix_judge_sandboxes_organization_id", table_name="judge_sandboxes")
    op.drop_table("judge_sandboxes")
