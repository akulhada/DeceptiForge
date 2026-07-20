# Purpose: the common security-export adapter contract + transport abstraction.
# Responsibilities: define the minimal HTTP transport (injectable, so no real network in tests), the
#   request an adapter builds from an already-minimized canonical envelope, and the adapter protocol
#   (build_request, classify_response, redact_error, health_check). Adapters never touch the DB and
#   never log credentials. Dependencies: integrations domain, retry.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.models.domain.integrations import DeliveryResult, RetryDecision, SecurityEventEnvelope
from app.services.integrations import retry


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    # Bounded response snippet only (never the full body); adapters must not log it.
    body_snippet: str = ""


class TransportError(Exception):
    """A connection/DNS/timeout failure. Carries no secret."""


class HttpTransport(Protocol):
    def send(self, request: HttpRequest, *, timeout: float) -> HttpResponse: ...


@dataclass(frozen=True)
class AdapterConfig:
    endpoint: str
    secret: str | None
    options: dict[str, str]


class SecurityExportAdapter(Protocol):
    integration_type: str

    def validate_configuration(self, config: AdapterConfig) -> None: ...
    def build_request(
        self, envelope: SecurityEventEnvelope, config: AdapterConfig, *, delivery_id: str
    ) -> HttpRequest: ...
    def classify_response(self, response: HttpResponse) -> DeliveryResult: ...
    def redact_error(self, error: Exception) -> str: ...


def result_from_response(response: HttpResponse) -> DeliveryResult:
    """Shared response classification used by every adapter unless it overrides."""
    decision = retry.classify_status(response.status)
    return DeliveryResult(
        decision=decision,
        response_status=response.status,
        safe_error_code=None if decision == RetryDecision.SUCCESS else f"http_{response.status}",
        retry_after_seconds=retry.parse_retry_after(response.headers.get("retry-after")),
    )


def result_from_transport_error() -> DeliveryResult:
    return DeliveryResult(
        decision=retry.classify_transport_error(), response_status=None,
        safe_error_code="transport_error",
    )
