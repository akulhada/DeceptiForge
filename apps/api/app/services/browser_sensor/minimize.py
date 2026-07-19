# Purpose: minimize browser paste event metadata so pasted text and conversation content are never
#   persisted.
# Responsibilities: reject/drop any field that could carry raw pasted text, model output, or
#   conversation, bound the number and length of fields, and serialize to a bounded safe string.
#   Deterministic. No model access.
from __future__ import annotations

import json
from typing import Any

# Keys that could carry raw pasted/model/conversation content — always dropped.
_FORBIDDEN_KEYS = frozenset(
    {
        "text", "pasted", "pasted_text", "paste", "value", "excerpt", "selection", "clipboard",
        "content", "body", "prompt", "prompts", "input", "inputs", "output", "outputs", "answer",
        "completion", "response", "responses", "message", "messages", "conversation", "history",
        "chunk", "chunks", "document", "raw", "html", "innertext", "textcontent",
    }
)
_MAX_FIELDS = 10
_MAX_VALUE_LEN = 96
_MAX_INPUT_VALUE_LEN = 256  # values longer than this are assumed to be raw content and dropped
_MAX_SERIALIZED = 1_024


def minimize_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    """Return only safe, bounded metadata fields. Forbidden/oversized fields are dropped."""
    out: dict[str, str] = {}
    for key, value in metadata.items():
        if key.lower() in _FORBIDDEN_KEYS:
            continue
        text = value if isinstance(value, str) else json.dumps(value, default=str)
        if len(text) > _MAX_INPUT_VALUE_LEN:
            continue  # oversized -> likely raw content
        out[str(key)[:48]] = text[:_MAX_VALUE_LEN]
        if len(out) >= _MAX_FIELDS:
            break
    return out


def serialize_metadata(metadata: dict[str, str]) -> str:
    return json.dumps(metadata, separators=(",", ":"))[:_MAX_SERIALIZED]
