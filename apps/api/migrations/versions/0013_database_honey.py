"""Database honey records: connectors, schema snapshots, deployments, rows, jobs, audit.

Purpose: add PostgreSQL connectors (encrypted credential), schema snapshots (metadata only), and
reviewable synthetic-row deployments with owned records, an async work queue, and an audit log.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_database_honey"
down_revision = "0012_deployment_tripwires"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "database_connectors",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("engine", sa.String(length=16), nullable=False, server_default="postgresql"),
        sa.Column("host_reference", sa.String(length=512), nullable=False),
        sa.Column("database_name", sa.String(length=255), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("secret_key_version", sa.String(length=32), nullable=False),
        sa.Column("ssl_mode", sa.String(length=16), nullable=False, server_default="require"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("read_only_mode", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_actor_id", sa.Uuid(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_schema_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("safe_error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_database_connectors_status", "database_connectors", ["status"])
    op.create_table(
        "database_schema_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("connector_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("database_version", sa.String(length=128), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False, index=True),
        sa.Column("data", sa.Text(), nullable=False),
    )
    op.create_table(
        "database_honey_deployments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("connector_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("schema_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("target_schema", sa.String(length=255), nullable=False),
        sa.Column("target_table", sa.String(length=255), nullable=False),
        sa.Column("decoy_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, index=True),
        sa.Column("requested_by_actor_id", sa.Uuid(), nullable=True),
        sa.Column("approved_by_actor_id", sa.Uuid(), nullable=True),
        sa.Column("preview_hash", sa.String(length=64), nullable=True),
        sa.Column("preview_data", sa.Text(), nullable=True),
        sa.Column("replaced_by_deployment_id", sa.Uuid(), nullable=True),
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
        "database_honey_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("deployment_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("decoy_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("trace_id", sa.String(length=128), nullable=False, index=True),
        sa.Column("target_primary_key", sa.Text(), nullable=False),
        sa.Column("row_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("inserted_values_encrypted", sa.Text(), nullable=False),
        sa.Column("verification_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="planned"),
        sa.Column("inserted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("deployment_id", "row_fingerprint", name="uq_honey_record_fingerprint"),
    )
    op.create_table(
        "database_honey_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("deployment_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("deployment_id", "job_type", name="uq_honey_job"),
    )
    op.create_index("ix_database_honey_jobs_status", "database_honey_jobs", ["status"])
    op.create_index("ix_database_honey_jobs_created_at", "database_honey_jobs", ["created_at"])
    op.create_table(
        "database_honey_audit",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("deployment_id", sa.Uuid(), nullable=True, index=True),
        sa.Column("connector_id", sa.Uuid(), nullable=True, index=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False, index=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("safe_metadata", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("database_honey_audit")
    op.drop_table("database_honey_jobs")
    op.drop_table("database_honey_records")
    op.drop_table("database_honey_deployments")
    op.drop_table("database_schema_snapshots")
    op.drop_table("database_connectors")
