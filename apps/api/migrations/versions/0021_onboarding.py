"""Guided onboarding state derived from existing tenant-scoped product records."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_onboarding"
down_revision = "0020_capacity_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("onboarding_workspaces", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("organization_id", sa.Uuid(), nullable=False, unique=True), sa.Column("status", sa.String(24), nullable=False), sa.Column("current_phase", sa.String(32), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("activated_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("onboarding_version", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_onboarding_workspaces_organization", "onboarding_workspaces", ["organization_id"])
    op.create_table("onboarding_steps", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("organization_id", sa.Uuid(), nullable=False), sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("onboarding_workspaces.id"), nullable=False), sa.Column("phase", sa.String(32), nullable=False), sa.Column("step_key", sa.String(64), nullable=False), sa.Column("status", sa.String(24), nullable=False), sa.Column("blocked_reason_code", sa.String(64)), sa.Column("safe_blocked_message", sa.String(512)), sa.Column("evidence", sa.Text(), nullable=False, server_default="{}"), sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("workspace_id", "step_key", name="uq_onboarding_step"))
    op.create_index("ix_onboarding_steps_org", "onboarding_steps", ["organization_id"])
    op.create_table("onboarding_recommendations", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("organization_id", sa.Uuid(), nullable=False), sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("onboarding_workspaces.id"), nullable=False), sa.Column("recommendation_type", sa.String(64), nullable=False), sa.Column("target_surface_type", sa.String(32), nullable=False), sa.Column("target_resource_id", sa.Uuid()), sa.Column("priority", sa.Integer(), nullable=False), sa.Column("expected_activation_gain", sa.Float(), nullable=False), sa.Column("expected_coverage_gain", sa.Float(), nullable=False), sa.Column("implementation_effort", sa.String(16), nullable=False), sa.Column("risk", sa.String(16), nullable=False), sa.Column("explanation", sa.String(1024), nullable=False), sa.Column("status", sa.String(16), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_onboarding_recommendations_org", "onboarding_recommendations", ["organization_id"])
    op.create_table("detection_test_runs", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("organization_id", sa.Uuid(), nullable=False), sa.Column("requested_by_actor_id", sa.Uuid()), sa.Column("deployment_id", sa.Uuid(), nullable=False), sa.Column("trace_identifier", sa.String(128), nullable=False), sa.Column("status", sa.String(16), nullable=False), sa.Column("expected_event_type", sa.String(64), nullable=False), sa.Column("observed_event_id", sa.Uuid()), sa.Column("alert_id", sa.Uuid()), sa.Column("incident_id", sa.Uuid()), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("safe_failure_code", sa.String(64)))
    op.create_index("ix_detection_test_runs_org", "detection_test_runs", ["organization_id"])
    op.create_index("ix_detection_test_runs_trace", "detection_test_runs", ["trace_identifier"])


def downgrade() -> None:
    op.drop_table("detection_test_runs")
    op.drop_table("onboarding_recommendations")
    op.drop_table("onboarding_steps")
    op.drop_table("onboarding_workspaces")
