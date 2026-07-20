"""Tenant capacity policy and immutable synthetic performance certifications."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_capacity_management"
down_revision = "0019_reliability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_limits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("tier", sa.String(length=16), nullable=False),
        sa.Column("monitoring_events_per_second", sa.Integer(), nullable=False),
        sa.Column("monitoring_burst", sa.Integer(), nullable=False),
        sa.Column("max_pending_jobs", sa.Integer(), nullable=False),
        sa.Column("max_concurrent_scans", sa.Integer(), nullable=False),
        sa.Column("max_concurrent_deployments", sa.Integer(), nullable=False),
        sa.Column("max_report_jobs", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by_actor_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tenant_limits_organization", "tenant_limits", ["organization_id"])
    op.create_table(
        "performance_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("methodology_version", sa.String(length=64), nullable=False),
        sa.Column("code_revision", sa.String(length=128), nullable=False),
        sa.Column("infrastructure", sa.Text(), nullable=False),
        sa.Column("workload", sa.Text(), nullable=False),
        sa.Column("results", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_performance_runs_status", "performance_runs", ["status"])
    op.create_index("ix_performance_runs_methodology", "performance_runs", ["methodology_version"])


def downgrade() -> None:
    op.drop_table("performance_runs")
    op.drop_table("tenant_limits")
