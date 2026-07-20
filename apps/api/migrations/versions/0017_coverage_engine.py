"""Measured coverage engine: immutable snapshots, pre-aggregated surfaces, gaps, recommendations,
policy, and audit.

Purpose: add organization-scoped, deterministic coverage snapshots (immutable), a pre-aggregated
surface inventory for fast reads, per-snapshot blind spots and ranked placement recommendations, a
versioned coverage policy, and an audit log. GPT never contributes to scoring.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_coverage_engine"
down_revision = "0016_agent_sensors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "coverage_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("covered_weight", sa.Float(), nullable=False),
        sa.Column("total_weight", sa.Float(), nullable=False),
        sa.Column("unknown_weight", sa.Float(), nullable=False),
        sa.Column("active_decoys", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_sensors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unhealthy_sensors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expired_decoys", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blind_spot_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("methodology_version", sa.String(length=32), nullable=False),
        sa.Column("source_state_hash", sa.String(length=64), nullable=False),
        sa.Column("surfaces_data", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_coverage_snapshots_calculated", "coverage_snapshots", ["calculated_at"])
    op.create_index("ix_coverage_snapshots_method", "coverage_snapshots", ["methodology_version"])
    op.create_index("ix_coverage_snapshots_hash", "coverage_snapshots", ["source_state_hash"])

    op.create_table(
        "coverage_surfaces",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("surface_type", sa.String(length=16), nullable=False),
        sa.Column("external_or_resource_id", sa.String(length=512), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("criticality", sa.Float(), nullable=False),
        sa.Column("exposure_score", sa.Float(), nullable=False),
        sa.Column("sensitivity_score", sa.Float(), nullable=False),
        sa.Column("attack_likelihood", sa.Float(), nullable=False),
        sa.Column("business_impact", sa.Float(), nullable=False),
        sa.Column("coverage_requirement", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("risk_weight", sa.Float(), nullable=False),
        sa.Column("surface_coverage", sa.Float(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="known"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id", "surface_type", "external_or_resource_id",
            name="uq_coverage_surface",
        ),
    )
    op.create_index("ix_coverage_surfaces_type", "coverage_surfaces", ["surface_type"])

    op.create_table(
        "coverage_gaps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("surface_type", sa.String(length=16), nullable=False),
        sa.Column("external_or_resource_id", sa.String(length=512), nullable=False),
        sa.Column("gap_type", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=512), nullable=False),
        sa.Column("missing_controls", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("recommended_decoy_type", sa.String(length=64), nullable=True),
        sa.Column("recommended_sensor_type", sa.String(length=64), nullable=True),
        sa.Column("expected_coverage_gain", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_coverage_gaps_snapshot", "coverage_gaps", ["snapshot_id"])
    op.create_index("ix_coverage_gaps_type", "coverage_gaps", ["gap_type"])
    op.create_index("ix_coverage_gaps_severity", "coverage_gaps", ["severity"])

    op.create_table(
        "coverage_recommendations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("surface_type", sa.String(length=16), nullable=False),
        sa.Column("external_or_resource_id", sa.String(length=512), nullable=False),
        sa.Column("recommended_action", sa.String(length=32), nullable=False),
        sa.Column("recommended_decoy_type", sa.String(length=64), nullable=True),
        sa.Column("target_location", sa.String(length=512), nullable=False),
        sa.Column("expected_coverage_gain", sa.Float(), nullable=False),
        sa.Column("expected_detection_gain", sa.Float(), nullable=False),
        sa.Column("deployment_risk", sa.Float(), nullable=False),
        sa.Column("false_positive_risk", sa.Float(), nullable=False),
        sa.Column("implementation_effort", sa.Float(), nullable=False),
        sa.Column("priority_score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("explanation", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_coverage_recs_snapshot", "coverage_recommendations", ["snapshot_id"])
    op.create_index("ix_coverage_recs_priority", "coverage_recommendations", ["priority_score"])

    op.create_table(
        "coverage_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("data", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", name="uq_coverage_policy_org"),
    )

    op.create_table(
        "coverage_audit",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("safe_metadata", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_coverage_audit_event_type", "coverage_audit", ["event_type"])


def downgrade() -> None:
    op.drop_table("coverage_audit")
    op.drop_table("coverage_policies")
    op.drop_table("coverage_recommendations")
    op.drop_table("coverage_gaps")
    op.drop_table("coverage_surfaces")
    op.drop_table("coverage_snapshots")
