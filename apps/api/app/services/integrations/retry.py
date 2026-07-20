# Purpose: versioned, deterministic retry classification and backoff for deliveries.
# Responsibilities: classify an HTTP status / transport error into retry / permanent / success,
#   parse Retry-After, and compute exponential backoff with bounded jitter. Deterministic given a
#   seed so tests are stable. No network. Dependencies: integrations domain.
from __future__ import annotations

import hashlib

from app.models.domain.integrations import RetryDecision

# Retryable statuses: transient. 408 request timeout, 429 too many requests, all 5xx.
_RETRYABLE_STATUS = frozenset({408, 429})


def classify_status(status: int) -> RetryDecision:
    if 200 <= status < 300:
        return RetryDecision.SUCCESS
    if status in _RETRYABLE_STATUS or 500 <= status <= 599:
        return RetryDecision.RETRY
    # Everything else (401/403 invalid creds/forbidden, 400/422 malformed, 404) is permanent.
    return RetryDecision.PERMANENT


def classify_transport_error() -> RetryDecision:
    """A connection timeout / DNS / network error is transient -> retry."""
    return RetryDecision.RETRY


def parse_retry_after(value: str | None) -> int | None:
    if not value:
        return None
    try:
        seconds = int(value.strip())
    except ValueError:
        return None
    return max(0, min(seconds, 3600))


def _jitter(attempt: int, key: str, spread: float) -> float:
    digest = hashlib.sha256(f"{key}:{attempt}".encode()).digest()
    frac = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
    return frac * spread


def backoff_seconds(
    attempt: int, *, base: float = 2.0, cap: float = 900.0, key: str = "", jitter: bool = True
) -> float:
    """Exponential backoff with bounded deterministic jitter (seeded by key+attempt)."""
    raw = float(min(cap, base * (2 ** max(0, attempt - 1))))
    if not jitter:
        return raw
    return float(round(raw + _jitter(attempt, key, min(raw * 0.25, 30.0)), 3))
