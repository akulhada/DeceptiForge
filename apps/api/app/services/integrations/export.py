# Purpose: render canonical security events into analyst-facing export formats.
# Responsibilities: format one or more minimized SecurityEventEnvelopes as JSON, JSON Lines, a CSV
#   summary, a Markdown incident report, or a minimal STIX 2.1 bundle. Never emits raw evidence or
#   secrets (envelopes are already minimized). STIX maps conservatively — synthetic decoy markers
#   are never labeled malicious indicators. Deterministic. Dependencies: integrations domain.
from __future__ import annotations

import csv
import io
import json
from collections.abc import Sequence

from app.models.domain.integrations import SCHEMA_VERSION, SecurityEventEnvelope

ExportFormat = str  # one of: json, jsonl, csv, markdown, stix


def _dump(envelope: SecurityEventEnvelope) -> dict:  # type: ignore[type-arg]
    result: dict = json.loads(envelope.model_dump_json())  # type: ignore[type-arg]
    return result


def render(envelopes: Sequence[SecurityEventEnvelope], fmt: ExportFormat) -> tuple[str, str]:
    """Return (content_type, body) for the requested format."""
    if fmt == "json":
        return "application/json", json.dumps([_dump(e) for e in envelopes], indent=2)
    if fmt == "jsonl":
        return "application/x-ndjson", "\n".join(json.dumps(_dump(e)) for e in envelopes)
    if fmt == "csv":
        return "text/csv", _csv(envelopes)
    if fmt == "markdown":
        return "text/markdown", _markdown(envelopes)
    if fmt == "stix":
        return "application/json", json.dumps(_stix_bundle(envelopes), indent=2)
    raise ValueError(f"unsupported export format: {fmt}")


def _csv(envelopes: Sequence[SecurityEventEnvelope]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["event_id", "event_type", "severity", "occurred_at", "title", "source_object_id",
         "affected_surfaces"]
    )
    for e in envelopes:
        writer.writerow([
            e.event_id, e.event_type.value, e.severity.value, e.occurred_at.isoformat(), e.title,
            e.source_object_id, ";".join(e.affected_surfaces),
        ])
    return buffer.getvalue()


def _markdown(envelopes: Sequence[SecurityEventEnvelope]) -> str:
    lines = ["# DeceptiForge incident report", ""]
    for e in envelopes:
        lines += [
            f"## {e.title}",
            f"- **Event**: `{e.event_type.value}`",
            f"- **Severity**: {e.severity.value} (confidence {e.confidence:.2f})",
            f"- **Occurred**: {e.occurred_at.isoformat()}",
            f"- **Source**: {e.source_object_type.value} `{e.source_object_id}`",
            f"- **Affected surfaces**: {', '.join(e.affected_surfaces) or '—'}",
            f"- **Summary**: {e.summary or '—'}",
        ]
        if e.deterministic_evidence_summary:
            lines.append(f"- **Deterministic evidence**: {e.deterministic_evidence_summary}")
        if e.narrative_summary:
            lines.append(f"- **AI narrative (non-authoritative)**: {e.narrative_summary}")
        if e.recommended_actions:
            lines.append("- **Recommended actions**:")
            lines += [f"  - {a}" for a in e.recommended_actions]
        lines.append("")
    return "\n".join(lines)


def _stix_bundle(envelopes: Sequence[SecurityEventEnvelope]) -> dict:  # type: ignore[type-arg]
    """A minimal, conservative STIX 2.1 bundle. Uses a versioned custom DeceptiForge extension and a
    Note for the deterministic summary. Synthetic decoy markers are never emitted as malicious
    Indicators — they are recorded as Observed Data / Notes only."""
    objects: list[dict] = []  # type: ignore[type-arg]
    for e in envelopes:
        objects.append({
            "type": "note",
            "spec_version": "2.1",
            "id": f"note--{e.event_id[:36]}",
            "abstract": e.title,
            "content": e.summary or e.deterministic_evidence_summary or e.title,
            "labels": ["deceptiforge", e.event_type.value],
            "x_deceptiforge_extension": {
                "extension_version": "df-stix-v1",
                "event_type": e.event_type.value,
                "severity": e.severity.value,
                "affected_surfaces": list(e.affected_surfaces),
                "authoritative": True,
                "synthetic_decoy": True,
            },
        })
    return {
        "type": "bundle",
        "id": f"bundle--{SCHEMA_VERSION}",
        "objects": objects,
    }
