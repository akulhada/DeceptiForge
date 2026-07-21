"""Controlled learning + calibration: normalized feature snapshots, immutable learning events,
placement outcomes, analyst feedback, operational results, and reviewed model versions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_learning"
down_revision = "0021_onboarding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feature_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id_hash", sa.String(64), nullable=False),
        sa.Column("feature_schema_version", sa.String(32), nullable=False),
        sa.Column("normalized_features", sa.Text(), nullable=False),
        sa.Column("feature_hash", sa.String(64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "feature_hash", name="uq_feature_snapshot"),
    )
    op.create_index(
        "ix_feature_snapshots_organization_id", "feature_snapshots", ["organization_id"]
    )
    op.create_index(
        "ix_feature_snapshots_org_captured", "feature_snapshots", ["organization_id", "captured_at"]
    )

    op.create_table(
        "placement_recommendation_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("source_feature_snapshot_id", sa.Uuid(), sa.ForeignKey("feature_snapshots.id")),
        sa.Column("recommendation_type", sa.String(64), nullable=False),
        sa.Column("target_zone", sa.String(64), nullable=False),
        sa.Column("target_category", sa.String(64), nullable=False, server_default=""),
        sa.Column("decoy_type", sa.String(64), nullable=False, server_default=""),
        sa.Column("rank", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reasoning_codes", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("engine_version", sa.String(32), nullable=False, server_default=""),
        sa.Column("model_version_id", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_placement_reco_organization_id", "placement_recommendation_records", ["organization_id"]
    )
    op.create_index(
        "ix_placement_reco_snapshot",
        "placement_recommendation_records",
        ["source_feature_snapshot_id"],
    )
    op.create_index("ix_placement_reco_zone", "placement_recommendation_records", ["target_zone"])
    op.create_index(
        "ix_placement_reco_org_created",
        "placement_recommendation_records",
        ["organization_id", "created_at"],
    )

    op.create_table(
        "placement_outcomes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "recommendation_id",
            sa.Uuid(),
            sa.ForeignKey("placement_recommendation_records.id"),
            nullable=False,
        ),
        sa.Column("outcome_type", sa.String(32), nullable=False),
        sa.Column("outcome_reason_code", sa.String(64)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("safe_metadata", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("recommendation_id", "outcome_type", name="uq_placement_outcome"),
    )
    op.create_index(
        "ix_placement_outcomes_organization_id", "placement_outcomes", ["organization_id"]
    )
    op.create_index(
        "ix_placement_outcomes_recommendation", "placement_outcomes", ["recommendation_id"]
    )
    op.create_index("ix_placement_outcomes_type", "placement_outcomes", ["outcome_type"])
    op.create_index(
        "ix_placement_outcomes_org_observed",
        "placement_outcomes",
        ["organization_id", "observed_at"],
    )

    op.create_table(
        "analyst_feedback",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid()),
        sa.Column("target_kind", sa.String(24), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("feedback_type", sa.String(32), nullable=False),
        sa.Column("original_value", sa.String(64)),
        sa.Column("corrected_value", sa.String(64)),
        sa.Column("normalized_comment", sa.String(512)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "actor_id",
            "target_kind",
            "target_id",
            "revision",
            name="uq_analyst_feedback_revision",
        ),
    )
    op.create_index("ix_analyst_feedback_organization_id", "analyst_feedback", ["organization_id"])
    op.create_index("ix_analyst_feedback_actor", "analyst_feedback", ["actor_id"])
    op.create_index("ix_analyst_feedback_type", "analyst_feedback", ["feedback_type"])
    op.create_index(
        "ix_analyst_feedback_target",
        "analyst_feedback",
        ["organization_id", "target_kind", "target_id"],
    )

    op.create_table(
        "learning_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("feature_snapshot_id", sa.Uuid()),
        sa.Column("recommendation_id", sa.Uuid()),
        sa.Column("placement_outcome_id", sa.Uuid()),
        sa.Column("analyst_feedback_id", sa.Uuid()),
        sa.Column("operational_result_id", sa.Uuid()),
        sa.Column("source_event_id", sa.Uuid()),
        sa.Column("actor_id", sa.Uuid()),
        sa.Column("engine_version", sa.String(32), nullable=False, server_default=""),
        sa.Column("feature_schema_version", sa.String(32), nullable=False, server_default=""),
        sa.Column("event_hash", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "event_hash", name="uq_learning_event"),
    )
    op.create_index("ix_learning_events_organization_id", "learning_events", ["organization_id"])
    op.create_index("ix_learning_events_recommendation", "learning_events", ["recommendation_id"])
    op.create_index(
        "ix_learning_events_org_type_occurred",
        "learning_events",
        ["organization_id", "event_type", "occurred_at"],
    )

    op.create_table(
        "learning_model_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid()),
        sa.Column("scope", sa.String(16), nullable=False, server_default="organization"),
        sa.Column("algorithm_name", sa.String(64), nullable=False),
        sa.Column("algorithm_version", sa.String(32), nullable=False),
        sa.Column("feature_schema_version", sa.String(32), nullable=False),
        sa.Column("methodology_version", sa.String(32), nullable=False, server_default=""),
        sa.Column("training_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("training_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("training_event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("weights", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("metrics", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("report", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("parent_version_id", sa.Uuid()),
        sa.Column("status", sa.String(16), nullable=False, server_default="candidate"),
        sa.Column("requested_by_actor_id", sa.Uuid()),
        sa.Column("approved_by_actor_id", sa.Uuid()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("rollback_reason", sa.String(256)),
        sa.Column(
            "safety_constraints_preserved", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_learning_versions_organization_id", "learning_model_versions", ["organization_id"]
    )
    op.create_index("ix_learning_versions_status", "learning_model_versions", ["status"])
    op.create_index(
        "ix_learning_versions_org_status", "learning_model_versions", ["organization_id", "status"]
    )
    op.create_index(
        "ix_learning_versions_algorithm",
        "learning_model_versions",
        ["algorithm_name", "algorithm_version"],
    )
    op.create_index(
        "ix_learning_versions_window",
        "learning_model_versions",
        ["training_window_start", "training_window_end"],
    )

    op.create_table(
        "operational_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("operation_type", sa.String(48), nullable=False),
        sa.Column("source_id", sa.Uuid()),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("latency_ms", sa.Float()),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_category", sa.String(64)),
        sa.Column("sensor_health", sa.Float()),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_operational_results_organization_id", "operational_results", ["organization_id"]
    )
    op.create_index("ix_operational_results_type", "operational_results", ["operation_type"])
    op.create_index(
        "ix_operational_results_org_observed",
        "operational_results",
        ["organization_id", "observed_at"],
    )


def downgrade() -> None:
    op.drop_table("operational_results")
    op.drop_table("learning_model_versions")
    op.drop_table("learning_events")
    op.drop_table("analyst_feedback")
    op.drop_table("placement_outcomes")
    op.drop_table("placement_recommendation_records")
    op.drop_table("feature_snapshots")
