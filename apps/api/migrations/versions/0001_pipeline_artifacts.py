"""Pipeline artifact tables.

Purpose: create the JSON-blob-backed tables that persist each engine artifact for the API
vertical slice. Revision ID mirrors the initial schema for the deception pipeline.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_pipeline_artifacts"
down_revision = None
branch_labels = None
depends_on = None


def _timestamp() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)


def upgrade() -> None:
    op.create_table(
        "repositories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("root_path", sa.String(length=2048), nullable=False),
        sa.Column("profile", sa.Text(), nullable=False),
        _timestamp(),
    )
    for table in ("context_profiles", "placement_plans", "decoy_plans"):
        op.create_table(
            table,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "repository_id",
                sa.Uuid(),
                sa.ForeignKey("repositories.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("data", sa.Text(), nullable=False),
            _timestamp(),
        )
    op.create_table(
        "validation_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "decoy_plan_id",
            sa.Uuid(),
            sa.ForeignKey("decoy_plans.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("decoy_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("data", sa.Text(), nullable=False),
        _timestamp(),
    )
    for table in ("detection_events", "alerts"):
        op.create_table(
            table,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("trace_identifier", sa.String(length=128), nullable=False, index=True),
            sa.Column("decoy_id", sa.Uuid(), nullable=False, index=True),
            sa.Column("data", sa.Text(), nullable=False),
            _timestamp(),
        )
    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("data", sa.Text(), nullable=False),
        _timestamp(),
    )


def downgrade() -> None:
    for table in (
        "incidents",
        "alerts",
        "detection_events",
        "validation_reports",
        "decoy_plans",
        "placement_plans",
        "context_profiles",
        "repositories",
    ):
        op.drop_table(table)
