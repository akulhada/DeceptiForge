"""AI agent activity sensors: managed sensors, one-time enrollment tokens, deterministic scope
policies, scoped sessions, minimized activity events, scope violations, and audit.

Purpose: add per-install agent sensors (encrypted signing secret, separate scoped ingest key),
short-lived one-time enrollment tokens, deterministic scope policies, scoped sessions (sanitized
task summary), idempotent minimized activity events, explainable scope violations, and an audit log.
Events never persist prompts, file contents, command output, or model reasoning.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_agent_sensors"
down_revision = "0015_browser_sensors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_sensors",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("sensor_public_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("adapter_type", sa.String(length=48), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("secret_key_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("api_key_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("sensor_public_id", name="uq_agent_sensor_public_id"),
    )
    op.create_index("ix_agent_sensors_public_id", "agent_sensors", ["sensor_public_id"])
    op.create_index("ix_agent_sensors_status", "agent_sensors", ["status"])

    op.create_table(
        "agent_enrollment_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_actor_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_by_sensor_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_agent_enrollment_token_hash"),
    )
    op.create_index("ix_agent_enrollment_tokens_hash", "agent_enrollment_tokens", ["token_hash"])

    op.create_table(
        "agent_scope_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("allowed_paths", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("denied_paths", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("allowed_tools", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("denied_tools", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("allowed_resource_types", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("maximum_file_reads", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("maximum_sensitive_reads", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "allow_dependency_changes", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "allow_secret_file_access", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("allow_database_access", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("allow_network_access", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("sensor_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("repository_id", sa.Uuid(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("external_session_id", sa.String(length=128), nullable=False),
        sa.Column("agent_type", sa.String(length=48), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("task_summary_sanitized", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("scope_policy_id", sa.Uuid(), nullable=True),
        sa.Column("scope_data", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id", "external_session_id", name="uq_agent_session_external"
        ),
    )
    op.create_index("ix_agent_sessions_sensor", "agent_sessions", ["sensor_id"])
    op.create_index("ix_agent_sessions_status", "agent_sessions", ["status"])
    op.create_index("ix_agent_sessions_correlation", "agent_sessions", ["correlation_id"])

    op.create_table(
        "agent_activity_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("sensor_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("session_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("external_event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=True),
        sa.Column("normalized_path", sa.String(length=2048), nullable=True),
        sa.Column("path_class", sa.String(length=24), nullable=True),
        sa.Column("tool_name", sa.String(length=128), nullable=True),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id_hash", sa.String(length=128), nullable=True),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("decoy_id", sa.String(length=128), nullable=True),
        sa.Column("result_status", sa.String(length=32), nullable=False, server_default="ok"),
        sa.Column("minimized_metadata", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "external_event_id", name="uq_agent_event_idempotency"),
    )
    op.create_index("ix_agent_events_session", "agent_activity_events", ["session_id"])
    op.create_index("ix_agent_events_type", "agent_activity_events", ["event_type"])
    op.create_index("ix_agent_events_trace", "agent_activity_events", ["trace_id"])
    op.create_index("ix_agent_events_observed", "agent_activity_events", ["observed_at"])
    op.create_index("ix_agent_events_correlation", "agent_activity_events", ["correlation_id"])

    op.create_table(
        "agent_scope_violations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("session_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("event_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("violation_type", sa.String(length=48), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("policy_rule", sa.String(length=128), nullable=False),
        sa.Column("explanation", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_violations_session", "agent_scope_violations", ["session_id"])
    op.create_index("ix_agent_violations_type", "agent_scope_violations", ["violation_type"])
    op.create_index("ix_agent_violations_severity", "agent_scope_violations", ["severity"])

    op.create_table(
        "agent_sensor_audit",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("agent_sensor_id", sa.Uuid(), nullable=True, index=True),
        sa.Column("session_id", sa.Uuid(), nullable=True, index=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("safe_metadata", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_sensor_audit_event_type", "agent_sensor_audit", ["event_type"])


def downgrade() -> None:
    op.drop_table("agent_sensor_audit")
    op.drop_table("agent_scope_violations")
    op.drop_table("agent_activity_events")
    op.drop_table("agent_sessions")
    op.drop_table("agent_scope_policies")
    op.drop_table("agent_enrollment_tokens")
    op.drop_table("agent_sensors")
