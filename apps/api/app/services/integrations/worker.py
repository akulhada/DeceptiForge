# Purpose: the security-export delivery worker.
# Responsibilities: claim leased due deliveries, revalidate the endpoint for SSRF, build the
#   destination request via the adapter, send it through an injected transport, and record
#   delivered / retry (backoff, Retry-After, max attempts + age) / dead-letter deterministically.
#   Never runs in the ingestion path; a failed delivery never blocks core work. Dependencies:
#   repository, adapters, ssrf, retry, integrations domain, settings.
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.models.domain.integrations import RetryDecision, SecurityEventEnvelope
from app.repositories.integrations import IntegrationNotFoundError, IntegrationRepository
from app.services.integrations import retry
from app.services.integrations.adapter import (
    AdapterConfig,
    HttpTransport,
    TransportError,
    result_from_transport_error,
)
from app.services.integrations.adapters import get_adapter
from app.services.integrations.ssrf import SsrfError, validate_endpoint


def _hours_between(a: datetime, b: datetime) -> float:
    a = a if a.tzinfo else a.replace(tzinfo=UTC)
    return (b - a).total_seconds() / 3600.0


class DeliveryWorker:
    def __init__(self, session: Session, transport: HttpTransport, settings: Settings) -> None:
        self._session = session
        self._transport = transport
        self._settings = settings
        self._repo = IntegrationRepository(session, settings)

    def run_once(self, *, now: datetime | None = None) -> int:
        now = now or datetime.now(UTC)
        settings = self._settings
        claimed = self._repo.claim_deliveries(
            settings.security_export_worker_batch_size,
            settings.security_export_worker_lease_seconds,
        )
        for delivery in claimed:
            self._process(delivery, now)
        return len(claimed)

    def _process(self, delivery, now: datetime) -> None:  # type: ignore[no-untyped-def]
        import json as _json

        settings = self._settings
        try:
            integration = self._repo.get_integration(
                delivery.organization_id, delivery.integration_id
            )
        except IntegrationNotFoundError:
            self._repo.mark_dead_letter(delivery, reason="integration_missing", status_code=None)
            return
        if integration.status != "active":
            self._repo.mark_dead_letter(delivery, reason="integration_inactive", status_code=None)
            return
        # Revalidate the endpoint every delivery (config may have changed; defence in depth).
        try:
            validate_endpoint(integration.endpoint_reference, settings)
        except SsrfError:
            self._repo.mark_dead_letter(delivery, reason="ssrf_blocked", status_code=None)
            self._repo.add_audit(
                organization_id=delivery.organization_id, integration_id=integration.id,
                delivery_id=delivery.id, event_type="ssrf_rejected", request_id="worker",
            )
            return

        envelope = SecurityEventEnvelope.model_validate_json(delivery.envelope_data)
        adapter = get_adapter(integration.integration_type)
        config = AdapterConfig(
            endpoint=integration.endpoint_reference,
            secret=self._repo.resolve_secret(integration),
            options=_json.loads(integration.config_data or "{}"),
        )
        request = adapter.build_request(envelope, config, delivery_id=str(delivery.id))
        try:
            response = self._transport.send(
                request, timeout=settings.security_export_timeout_seconds
            )
            result = adapter.classify_response(response)
        except TransportError:
            result = result_from_transport_error()

        if result.decision == RetryDecision.SUCCESS:
            self._repo.mark_delivered(delivery, status_code=result.response_status)
            self._repo.set_status(integration, "active", success=True)
            return

        exhausted = (
            delivery.attempt_count + 1 >= settings.security_export_max_attempts
            or _hours_between(delivery.created_at, now) >= settings.security_export_max_age_hours
        )
        if result.decision == RetryDecision.PERMANENT:
            self._repo.mark_dead_letter(
                delivery, reason=result.safe_error_code or "permanent_failure",
                status_code=result.response_status,
            )
            self._repo.set_status(integration, "degraded", error="permanent_failure", failure=True)
        elif exhausted:
            self._repo.mark_dead_letter(
                delivery, reason="max_attempts_exceeded", status_code=result.response_status
            )
            self._repo.set_status(integration, "degraded", error="delivery_exhausted", failure=True)
        else:
            delay = result.retry_after_seconds
            if delay is None:
                delay = retry.backoff_seconds(delivery.attempt_count + 1, key=str(delivery.id))
            self._repo.mark_retry(
                delivery, delay_seconds=float(delay), error=result.safe_error_code,
                status_code=result.response_status,
            )
