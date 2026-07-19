"""AI/RAG/MCP tripwire sensors: connectors, deployments, minimized events, jobs, audit.

Purpose: add vector-store and MCP connectors (encrypted secrets), reviewable AI tripwire
deployments (inert synthetic assets), trusted minimized events, an async work queue, and an audit
log. Events never persist prompts, chunks, model outputs, or embeddings.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_ai_tripwires"
down_revision = "0013_database_honey"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rag_connectors",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("connector_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("secret_key_version", sa.String(length=32), nullable=False),
        sa.Column("index_or_collection", sa.String(length=255), nullable=False),
        sa.Column("namespace", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("created_by_actor_id", sa.Uuid(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("safe_error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rag_connectors_status", "rag_connectors", ["status"])
    op.create_table(
        "mcp_connectors",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("server_reference", sa.String(length=512), nullable=False),
        sa.Column("transport_type", sa.String(length=32), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=True),
        sa.Column("secret_key_version", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("created_by_actor_id", sa.Uuid(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("safe_error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mcp_connectors_status", "mcp_connectors", ["status"])
    op.create_table(
        "ai_tripwire_deployments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("surface_type", sa.String(length=16), nullable=False, index=True),
        sa.Column("connector_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("target_collection", sa.String(length=255), nullable=False),
        sa.Column("decoy_kind", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, index=True),
        sa.Column("trace_id", sa.String(length=128), nullable=False, index=True),
        sa.Column("external_asset_id", sa.String(length=512), nullable=True),
        sa.Column("requested_by_actor_id", sa.Uuid(), nullable=True),
        sa.Column("approved_by_actor_id", sa.Uuid(), nullable=True),
        sa.Column("preview_hash", sa.String(length=64), nullable=True),
        sa.Column("preview_data", sa.Text(), nullable=True),
        sa.Column("verification_hash", sa.String(length=64), nullable=True),
        sa.Column("monitoring_activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("safe_failure_code", sa.String(length=64), nullable=True),
        sa.Column("safe_failure_message", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "ai_tripwire_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("deployment_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("trace_id", sa.String(length=128), nullable=False, index=True),
        sa.Column("surface_type", sa.String(length=16), nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False, index=True),
        sa.Column("source_id", sa.String(length=256), nullable=False),
        sa.Column("monitor_identity", sa.String(length=128), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("minimized_metadata", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "ai_tripwire_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("deployment_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("deployment_id", "job_type", name="uq_ai_tripwire_job"),
    )
    op.create_index("ix_ai_tripwire_jobs_status", "ai_tripwire_jobs", ["status"])
    op.create_index("ix_ai_tripwire_jobs_created_at", "ai_tripwire_jobs", ["created_at"])
    op.create_table(
        "ai_tripwire_audit",
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
    op.drop_table("ai_tripwire_audit")
    op.drop_table("ai_tripwire_jobs")
    op.drop_table("ai_tripwire_events")
    op.drop_table("ai_tripwire_deployments")
    op.drop_table("mcp_connectors")
    op.drop_table("rag_connectors")
