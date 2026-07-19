# Purpose: emit structured operational metrics/logs for ingestion safety and lifecycle events.
# Responsibilities: provide one place to record counters/latencies (rate-limit decisions, replay
#   and signature rejections, body-size rejections, ingest latency, reconstruction queue depth,
#   retention results) as structured log records. Only safe fields are recorded: never secrets,
#   raw bodies, or decrypted evidence. Dependencies: stdlib logging.
from __future__ import annotations

import logging

_logger = logging.getLogger("deceptiforge.metrics")

# Fields that must never be logged, guarded defensively in case a caller passes them by mistake.
_FORBIDDEN = frozenset(
    {"api_key", "secret", "signing_secret", "signature", "nonce", "body", "evidence", "excerpt"}
)


def emit(event: str, **fields: object) -> None:
    """Record a structured metric event with only safe fields."""
    safe = {key: value for key, value in fields.items() if key not in _FORBIDDEN}
    _logger.info(event, extra={"event": event, **safe})
