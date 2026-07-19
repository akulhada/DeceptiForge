# Purpose: minimize AI tripwire event metadata so raw prompts/chunks/outputs/embeddings are never
#   persisted.
# Responsibilities: drop forbidden keys and oversized values, bound the number and length of fields,
#   and serialize to a bounded safe string. Deterministic. No model access.
from __future__ import annotations

import json
from typing import Any

# Keys that could carry raw model/customer content — always dropped.
_FORBIDDEN_KEYS = frozenset(
    {
        "prompt", "prompts", "output", "outputs", "completion", "completions", "answer", "answers",
        "chunk", "chunks", "content", "document", "documents", "text", "body", "embedding",
        "embeddings", "vector", "vectors", "message", "messages", "conversation", "history",
        "response", "responses", "raw", "context",
    }
)
_MAX_FIELDS = 12
_MAX_VALUE_LEN = 120
_MAX_INPUT_VALUE_LEN = 512  # values longer than this are assumed to be raw content and dropped
_MAX_SERIALIZED = 1024


def minimize_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    """Return only safe, bounded metadata fields."""
    out: dict[str, str] = {}
    for key, value in metadata.items():
        if key.lower() in _FORBIDDEN_KEYS:
            continue
        text = value if isinstance(value, str) else json.dumps(value, default=str)
        if len(text) > _MAX_INPUT_VALUE_LEN:
            continue  # oversized -> likely raw content
        out[str(key)[:64]] = text[:_MAX_VALUE_LEN]
        if len(out) >= _MAX_FIELDS:
            break
    return out


def serialize_metadata(metadata: dict[str, str]) -> str:
    return json.dumps(metadata, separators=(",", ":"))[:_MAX_SERIALIZED]
