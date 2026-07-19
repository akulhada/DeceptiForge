"""Decoy deployment approval and lifecycle.

Purpose: add reviewable, reversible decoy deployments (through a controlled branch + pull request),
their change-set items, approvals, an append-only audit log, and an async deployment work queue.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_decoy_deployments"
down_revision = "0010_alert_episode_uniqueness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decoy_deployments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("repository_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("scan_job_id", sa.Uuid(), nullable=True),
        sa.Column("decoy_plan_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("validation_report_decision", sa.String(length=16), nullable=False),
        sa.Column("requested_by_actor_id", sa.Uuid(), nullable=True),
        sa.Column("approved_by_actor_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, index=True),
        sa.Column("target_branch", sa.String(length=255), nullable=False),
        sa.Column("source_branch", sa.String(length=255), nullable=False),
        sa.Column("pull_request_number", sa.Integer(), nullable=True),
        sa.Column("pull_request_url", sa.String(length=1024), nullable=True),
        sa.Column("base_commit_sha", sa.String(length=64), nullable=False),
        sa.Column("deployed_commit_sha", sa.String(length=64), nullable=True),
        sa.Column("preview_hash", sa.String(length=64), nullable=True),
        sa.Column("preview_data", sa.Text(), nullable=True),
        sa.Column("monitoring_activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("safe_failure_message", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "decoy_deployment_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "deployment_id", sa.Uuid(), sa.ForeignKey("decoy_deployments.id"),
            nullable=False, index=True,
        ),
        sa.Column("decoy_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("target_path", sa.String(length=2048), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("trace_identifier", sa.String(length=128), nullable=False, index=True),
        sa.Column("original_content_hash", sa.String(length=64), nullable=True),
        sa.Column("proposed_content_hash", sa.String(length=64), nullable=False),
        sa.Column("deployed_content_hash", sa.String(length=64), nullable=True),
        sa.Column("content_data", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="planned"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "deployment_approvals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "deployment_id", sa.Uuid(), sa.ForeignKey("decoy_deployments.id"),
            nullable=False, index=True,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("comment", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "deployment_audit",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("deployment_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False, index=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("safe_metadata", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "deployment_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("deployment_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("deployment_id", "job_type", name="uq_deployment_job"),
    )
    op.create_index("ix_deployment_jobs_status", "deployment_jobs", ["status"])
    op.create_index("ix_deployment_jobs_created_at", "deployment_jobs", ["created_at"])


def downgrade() -> None:
    op.drop_table("deployment_jobs")
    op.drop_table("deployment_audit")
    op.drop_table("deployment_approvals")
    op.drop_table("decoy_deployment_items")
    op.drop_table("decoy_deployments")
