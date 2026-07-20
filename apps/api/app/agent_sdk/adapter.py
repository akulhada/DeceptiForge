# Purpose: the agent adapter contract plus a generic JSONL adapter and a local staging adapter.
# Responsibilities: normalize vendor/tool events into minimized activity events, never carrying file
#   content, command output, prompts, or model reasoning. Vendor-specific adapters stay isolated
#   behind this contract. Pure — no network, no agent execution.
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

_ALLOWED_EVENT_TYPES = frozenset(
    {
        "session_started", "session_completed", "file_listed", "file_read", "file_modified",
        "file_created", "file_deleted", "search_performed", "command_requested", "tool_invoked",
        "mcp_resource_listed", "mcp_resource_read", "database_query_requested",
        "network_request_requested", "decoy_touched", "sensitive_path_accessed",
        "denied_action_attempted",
    }
)
# Raw-content keys stripped before an event ever leaves the adapter.
_FORBIDDEN_KEYS = frozenset(
    {
        "content", "file_content", "source", "code", "diff", "patch", "body", "text", "prompt",
        "output", "command_output", "stdout", "stderr", "terminal", "reasoning",
        "chain_of_thought", "completion", "response", "query", "sql", "snippet",
    }
)


@dataclass(frozen=True)
class NormalizedEvent:
    external_event_id: str
    event_type: str
    path: str | None = None
    tool_name: str | None = None
    resource_type: str | None = None
    resource_id_hash: str | None = None
    trace_id: str | None = None
    result_status: str = "ok"
    metadata: dict[str, str] = field(default_factory=dict)

    def to_body(self, session_external_id: str) -> dict[str, Any]:
        return {
            "external_event_id": self.external_event_id,
            "session_external_id": session_external_id,
            "event_type": self.event_type,
            "path": self.path,
            "tool_name": self.tool_name,
            "resource_type": self.resource_type,
            "resource_id_hash": self.resource_id_hash,
            "trace_id": self.trace_id,
            "result_status": self.result_status,
            "metadata": self.metadata,
        }


class AdapterError(Exception):
    pass


def _strip(metadata: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in metadata.items():
        if k.lower() in _FORBIDDEN_KEYS:
            continue
        text = v if isinstance(v, str) else json.dumps(v, default=str)
        if len(text) > 256:
            continue
        out[str(k)[:48]] = text[:96]
        if len(out) >= 10:
            break
    return out


class AgentAdapter(Protocol):
    def capabilities(self) -> tuple[str, ...]: ...
    def normalize_event(self, raw: dict[str, Any]) -> NormalizedEvent: ...
    def health_check(self) -> bool: ...


class JsonlAdapter:
    """Generic adapter: each raw event is a JSON object with an id + type and optional path/tool.
    Any raw-content field is dropped. Unknown event types are rejected."""

    def capabilities(self) -> tuple[str, ...]:
        return ("jsonl", "stdin")

    def health_check(self) -> bool:
        return True

    def normalize_event(self, raw: dict[str, Any]) -> NormalizedEvent:
        event_type = str(raw.get("event_type", "")).strip()
        if event_type not in _ALLOWED_EVENT_TYPES:
            raise AdapterError(f"unknown event type: {event_type!r}")
        external_id = str(raw.get("id") or raw.get("external_event_id") or "").strip()
        if not external_id:
            raise AdapterError("event missing id")
        metadata_raw = raw.get("metadata")
        metadata = _strip(metadata_raw if isinstance(metadata_raw, dict) else {})
        return NormalizedEvent(
            external_event_id=external_id[:128],
            event_type=event_type,
            path=(str(raw["path"])[:4096] if raw.get("path") else None),
            tool_name=(str(raw["tool"])[:128] if raw.get("tool") else None),
            resource_type=(str(raw["resource_type"])[:64] if raw.get("resource_type") else None),
            resource_id_hash=(
                str(raw["resource_id_hash"])[:128] if raw.get("resource_id_hash") else None
            ),
            trace_id=(str(raw["trace_id"])[:128] if raw.get("trace_id") else None),
            result_status=str(raw.get("result_status", "ok"))[:32],
            metadata=metadata,
        )


class LocalFsAdapter(JsonlAdapter):
    """Staging adapter for local filesystem/tool telemetry. Maps a small set of local actions to
    minimized events; it never reads file contents — only paths and action types."""

    _ACTION_MAP = {
        "read": "file_read",
        "list": "file_listed",
        "write": "file_modified",
        "create": "file_created",
        "delete": "file_deleted",
        "search": "search_performed",
        "tool": "tool_invoked",
    }

    def capabilities(self) -> tuple[str, ...]:
        return ("local_fs", "tool_telemetry")

    def normalize_event(self, raw: dict[str, Any]) -> NormalizedEvent:
        if "action" in raw and "event_type" not in raw:
            mapped = self._ACTION_MAP.get(str(raw["action"]).lower())
            if mapped is None:
                raise AdapterError(f"unknown local action: {raw.get('action')!r}")
            raw = {**raw, "event_type": mapped}
        return super().normalize_event(raw)
