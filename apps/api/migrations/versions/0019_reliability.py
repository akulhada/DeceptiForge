"""Multi-region reliability: failover events, restore drills, and reliability audit.

Purpose: add an audited failover control-plane trail (region/epoch attribution, operator, SoD),
recorded restore drills (achieved RPO/RTO + signed check report, no secrets), and a reliability
audit log. No tenant data here — these are operational records.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_reliability"
down_revision = "0018_security_integrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "failover_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("from_state", sa.String(length=24), nullable=False),
        sa.Column("to_state", sa.String(length=24), nullable=False),
        sa.Column("deployment_region", sa.String(length=64), nullable=False),
        sa.Column("cluster_id", sa.String(length=64), nullable=False),
        sa.Column("active_region_epoch", sa.Integer(), nullable=False),
        sa.Column("requested_by_actor_id", sa.Uuid(), nullable=True),
        sa.Column("approved_by_actor_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("safe_metadata", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_failover_events_to_state", "failover_events", ["to_state"])
    op.create_index("ix_failover_events_created", "failover_events", ["created_at"])

    op.create_table(
        "restore_drills",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("backup_identifier", sa.String(length=128), nullable=False),
        sa.Column("recovery_point", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("achieved_rpo_minutes", sa.Float(), nullable=True),
        sa.Column("achieved_rto_minutes", sa.Float(), nullable=True),
        sa.Column("migration_revision", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("checksum", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("report_data", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("deployment_region", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("requested_by_actor_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_restore_drills_created", "restore_drills", ["created_at"])

    op.create_table(
        "reliability_audit",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("deployment_region", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("safe_metadata", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reliability_audit_event_type", "reliability_audit", ["event_type"])


def downgrade() -> None:
    op.drop_table("reliability_audit")
    op.drop_table("restore_drills")
    op.drop_table("failover_events")
