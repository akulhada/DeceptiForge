# Purpose: define the versioned canonical signing format for monitor ingestion requests.
# Responsibilities: build a stable canonical payload from the request identity, compute an
#   HMAC-SHA256 signature, and verify a provided signature in constant time. The signing input binds
#   method, path, organization, monitor, timestamp, nonce, and a hash of the exact request body, so
#   any modification to those fields invalidates the signature. Dependencies: stdlib hmac/hashlib.
from __future__ import annotations

import hashlib
import hmac

SIGNATURE_VERSION = "monitor-signature-v1"
# Documented clock-skew window is enforced by the replay guard (monitoring_timestamp_skew_seconds).


def body_sha256(body: bytes) -> str:
    """Hash the exact received request bytes."""
    return hashlib.sha256(body).hexdigest()


def canonical_request(
    *,
    method: str,
    path: str,
    organization_id: str,
    monitor_id: str,
    timestamp: str,
    nonce: str,
    body: bytes,
) -> str:
    """Return the canonical monitor-signature-v1 payload with stable newline separators.

    The HTTP method is normalized to uppercase; the path is used exactly as received. Fields are
    UTF-8, newline-separated, with the version first so the format is self-describing.
    """
    return "\n".join(
        (
            SIGNATURE_VERSION,
            method.upper(),
            path,
            organization_id,
            monitor_id,
            timestamp,
            nonce,
            body_sha256(body),
        )
    )


def sign(secret: str, canonical: str) -> str:
    """Compute the hex HMAC-SHA256 signature over the canonical payload."""
    return hmac.new(
        secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def verify(secret: str, canonical: str, provided_signature: str) -> bool:
    """Constant-time comparison of the expected and provided signatures."""
    expected = sign(secret, canonical)
    return hmac.compare_digest(expected, provided_signature)
