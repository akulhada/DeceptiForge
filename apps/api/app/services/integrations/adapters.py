# Purpose: the concrete SIEM/SOAR export adapters behind the common contract.
# Responsibilities: build a destination-specific HTTP request from an already-minimized canonical
#   envelope for generic signed webhook, Splunk HEC, Microsoft Sentinel, and Elastic. Each signs or
#   authenticates without ever logging the credential, sets a deterministic idempotency/document id,
#   and classifies responses via the shared rules. No DB access. Dependencies: adapter, signing,
#   integrations domain.
from __future__ import annotations

import json
import time

from app.models.domain.integrations import DeliveryResult, IntegrationType, SecurityEventEnvelope
from app.services.integrations.adapter import (
    AdapterConfig,
    HttpRequest,
    HttpResponse,
    result_from_response,
)
from app.services.monitor_signing import body_sha256, sign

_SIGNATURE_VERSION = "df-webhook-v1"


def _envelope_bytes(envelope: SecurityEventEnvelope) -> bytes:
    return envelope.model_dump_json().encode("utf-8")


def _redact(error: Exception) -> str:
    # Never echo the message (could contain a URL with a token); return the class only.
    return type(error).__name__


class WebhookAdapter:
    integration_type = IntegrationType.GENERIC_WEBHOOK.value

    def validate_configuration(self, config: AdapterConfig) -> None:
        if not config.secret:
            raise ValueError("generic webhook requires a signing secret")

    def build_request(
        self, envelope: SecurityEventEnvelope, config: AdapterConfig, *, delivery_id: str
    ) -> HttpRequest:
        body = _envelope_bytes(envelope)
        timestamp = str(int(time.time()))
        body_hash = body_sha256(body)
        canonical = "\n".join(
            (_SIGNATURE_VERSION, delivery_id, envelope.event_type.value, timestamp, body_hash)
        )
        signature = sign(config.secret or "", canonical)
        return HttpRequest(
            method="POST", url=config.endpoint, body=body,
            headers={
                "content-type": "application/json",
                "X-DeceptiForge-Delivery-ID": delivery_id,
                "X-DeceptiForge-Timestamp": timestamp,
                "X-DeceptiForge-Signature": signature,
                "X-DeceptiForge-Event": envelope.event_type.value,
                "X-DeceptiForge-Schema-Version": envelope.schema_version,
            },
        )

    def classify_response(self, response: HttpResponse) -> DeliveryResult:
        return result_from_response(response)

    def redact_error(self, error: Exception) -> str:
        return _redact(error)


class SplunkHecAdapter:
    integration_type = IntegrationType.SPLUNK_HEC.value

    def validate_configuration(self, config: AdapterConfig) -> None:
        if not config.secret:
            raise ValueError("Splunk HEC requires a token")

    def build_request(
        self, envelope: SecurityEventEnvelope, config: AdapterConfig, *, delivery_id: str
    ) -> HttpRequest:
        payload = {
            "event": json.loads(envelope.model_dump_json()),
            "source": config.options.get("source", "deceptiforge"),
            "sourcetype": config.options.get("sourcetype", "deceptiforge:security"),
            "index": config.options.get("index", "main"),
            # Splunk dedups on the event id when configured; carry a stable one.
            "fields": {"deceptiforge_delivery_id": delivery_id},
        }
        return HttpRequest(
            method="POST", url=config.endpoint,
            body=json.dumps(payload).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "Authorization": f"Splunk {config.secret}",  # never logged
            },
        )

    def classify_response(self, response: HttpResponse) -> DeliveryResult:
        return result_from_response(response)

    def redact_error(self, error: Exception) -> str:
        return _redact(error)


class SentinelAdapter:
    integration_type = IntegrationType.MICROSOFT_SENTINEL.value

    def validate_configuration(self, config: AdapterConfig) -> None:
        if not config.secret:
            raise ValueError("Sentinel ingestion requires a shared key / token")

    def build_request(
        self, envelope: SecurityEventEnvelope, config: AdapterConfig, *, delivery_id: str
    ) -> HttpRequest:
        # Transport-agnostic: a signed JSON POST compatible with a Logic App / ingestion endpoint.
        # The concrete Log Analytics signature can be swapped in without changing the contract.
        body = _envelope_bytes(envelope)
        return HttpRequest(
            method="POST", url=config.endpoint, body=body,
            headers={
                "content-type": "application/json",
                "Log-Type": config.options.get("log_type", "DeceptiForgeSecurity"),
                "Authorization": f"Bearer {config.secret}",  # never logged
                "X-DeceptiForge-Delivery-ID": delivery_id,
            },
        )

    def classify_response(self, response: HttpResponse) -> DeliveryResult:
        return result_from_response(response)

    def redact_error(self, error: Exception) -> str:
        return _redact(error)


class ElasticAdapter:
    integration_type = IntegrationType.ELASTIC.value

    def validate_configuration(self, config: AdapterConfig) -> None:
        if not config.secret:
            raise ValueError("Elastic requires an API key")

    def build_request(
        self, envelope: SecurityEventEnvelope, config: AdapterConfig, *, delivery_id: str
    ) -> HttpRequest:
        index = config.options.get("index", "deceptiforge-security")
        # PUT to a deterministic document id -> a duplicate delivery is an idempotent overwrite.
        url = f"{config.endpoint.rstrip('/')}/{index}/_doc/{delivery_id}"
        return HttpRequest(
            method="PUT", url=url, body=_envelope_bytes(envelope),
            headers={
                "content-type": "application/json",
                "Authorization": f"ApiKey {config.secret}",  # never logged
            },
        )

    def classify_response(self, response: HttpResponse) -> DeliveryResult:
        return result_from_response(response)

    def redact_error(self, error: Exception) -> str:
        return _redact(error)


_ADAPTERS: dict[str, type] = {
    IntegrationType.GENERIC_WEBHOOK.value: WebhookAdapter,
    IntegrationType.SPLUNK_HEC.value: SplunkHecAdapter,
    IntegrationType.MICROSOFT_SENTINEL.value: SentinelAdapter,
    IntegrationType.ELASTIC.value: ElasticAdapter,
}


def get_adapter(integration_type: str):  # type: ignore[no-untyped-def]
    cls = _ADAPTERS.get(integration_type)
    if cls is None:
        raise ValueError(f"unsupported integration type: {integration_type}")
    return cls()
