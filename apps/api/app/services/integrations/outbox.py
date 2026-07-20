# Purpose: transactional-outbox emission — turn one canonical event into per-integration delivery
#   rows in the caller's transaction.
# Responsibilities: find the active integrations whose declarative filters match, apply each
#   integration's payload profile (minimizing per destination), and enqueue one idempotent delivery
#   row each. Runs inside the same DB transaction as the source alert/incident commit, so no export
#   is lost and none is delivered synchronously. Dependencies: repository, profiles, integrations
#   domain, settings.
from __future__ import annotations

from uuid import UUID

from app.config.settings import Settings
from app.models.domain.integrations import PayloadProfile, SecurityEventEnvelope
from app.repositories.integrations import IntegrationRepository
from app.services.integrations import profiles


def emit_event(
    repo: IntegrationRepository,
    *,
    organization_id: UUID,
    envelope: SecurityEventEnvelope,
    settings: Settings,
    event_version: int = 1,
) -> int:
    """Enqueue a delivery for every matching active integration. Returns the number enqueued. Never
    performs network I/O; the delivery worker publishes later."""
    matches = repo.matching_integrations(organization_id, envelope)
    enqueued = 0
    for integration in matches:
        shaped = profiles.apply_profile(
            envelope, PayloadProfile(integration.payload_profile),
            include_narrative=integration.include_narrative,
            max_bytes=settings.security_export_max_payload_bytes,
        )
        if repo.enqueue_delivery(
            organization_id=organization_id, integration=integration, envelope=shaped,
            event_version=event_version,
        ) is not None:
            enqueued += 1
    return enqueued
