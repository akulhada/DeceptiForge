# Purpose: render deterministic, inert decoy file content for a deployment change set.
# Responsibilities: turn a DecoyAsset's metadata into a stable text file carrying an ownership
#   marker and the tripwire trace, using only redacted synthetic values — never real secrets, raw
#   payload bodies, credentials, or production endpoints. Dependencies: decoy domain models.
from __future__ import annotations

import hashlib
from uuid import UUID

from app.models.domain.decoy import DecoyAsset

_MARKER_PREFIX = "df-decoy-marker"


def deployment_marker(decoy_id: UUID) -> str:
    """Stable marker embedded in deployed content so retire/rollback can find only this decoy."""
    return f"{_MARKER_PREFIX}:{decoy_id}"


def content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _redacted_hint(asset: DecoyAsset) -> str:
    """A masked synthetic hint drawn from the payload, if any. Never a raw value."""
    payload = asset.payload
    for field in ("redacted_value", "redacted_endpoint", "display_value"):
        value = getattr(payload, field, None)
        if isinstance(value, str) and value:
            # Mask everything but a short prefix so the file stays inert and non-usable.
            return value[:4] + "…redacted"
    return "«synthetic»"


def render_decoy_content(asset: DecoyAsset) -> str:
    """Return the exact, deterministic file body for a decoy asset (inert; synthetic only)."""
    trace = asset.trigger_metadata.trace_identifier
    lines = (
        f"<!-- {deployment_marker(asset.decoy_id)} -->",
        "# DeceptiForge decoy — synthetic and inert (DO NOT USE)",
        "",
        "Deployed by DeceptiForge as a defensive decoy. It contains no real secrets,",
        "credentials, or production endpoints. Any access to it is a tripwire.",
        "",
        f"- decoy-type: {asset.decoy_type.value}",
        f"- trace: {trace}",
        f"- synthetic-hint: {_redacted_hint(asset)}",
        f"- deployment-marker: {deployment_marker(asset.decoy_id)}",
        "",
    )
    return "\n".join(lines)
