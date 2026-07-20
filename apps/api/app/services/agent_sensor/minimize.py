# Purpose: minimize agent activity event metadata so no raw content is ever persisted.
# Responsibilities: drop any field that could carry file content, command output, prompts, or model
#   reasoning; bound field count/length; serialize to a bounded safe string. Deterministic.
from __future__ import annotations

import json
from typing import Any

# Keys that could carry raw file/command/model content — always dropped.
_FORBIDDEN_KEYS = frozenset(
    {
        "content", "file_content", "source", "source_code", "code", "diff", "patch", "body",
        "text", "prompt", "prompts", "output", "outputs", "command_output", "stdout", "stderr",
        "terminal", "terminal_history", "reasoning", "chain_of_thought", "thought", "thoughts",
        "completion", "response", "responses", "message", "messages", "conversation", "history",
        "query", "sql", "raw", "snippet", "excerpt",
    }
)
_MAX_FIELDS = 10
_MAX_VALUE_LEN = 96
_MAX_INPUT_VALUE_LEN = 256  # values longer than this are assumed to be raw content and dropped
_MAX_SERIALIZED = 1_024


def minimize_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in metadata.items():
        if key.lower() in _FORBIDDEN_KEYS:
            continue
        text = value if isinstance(value, str) else json.dumps(value, default=str)
        if len(text) > _MAX_INPUT_VALUE_LEN:
            continue
        out[str(key)[:48]] = text[:_MAX_VALUE_LEN]
        if len(out) >= _MAX_FIELDS:
            break
    return out


def serialize_metadata(metadata: dict[str, str]) -> str:
    return json.dumps(metadata, separators=(",", ":"))[:_MAX_SERIALIZED]


def sanitize_task_summary(raw: str, *, max_len: int = 512) -> str:
    """Bound + strip control chars from a task summary. Never a raw conversation."""
    cleaned = "".join(ch for ch in raw if ch == "\n" or ch >= " ")
    cleaned = " ".join(cleaned.split())
    return cleaned[:max_len]
