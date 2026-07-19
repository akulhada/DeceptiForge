# Purpose: enforce that generated (and any operator-supplied) tripwire content is inert and safe.
# Responsibilities: reject prompt-injection, executable, destructive, or real-endpoint patterns in
#   document/resource content, restrict MCP URIs to the reserved synthetic scheme, and bound size.
#   Deterministic; the default is to reject. No model access. GPT never decides safety.
from __future__ import annotations

import re

_RESERVED_MCP_SCHEME = "deceptiforge://"

# Patterns that must never appear in inert decoy content.
_UNSAFE_PATTERNS = (
    r"ignore (all |the |previous|prior)",
    r"disregard (all |the |previous|prior)",
    r"you are now",
    r"\bact as\b",
    r"system prompt",
    r"jailbreak",
    r"\bexecute\b",
    r"run (the |this )",
    r"\bsudo\b",
    r"rm\s+-rf",
    r"curl\s",
    r"wget\s",
    r"https?://",
    r"file://",
    r"ssh://",
    r"```",
    r"<script",
    r"drop\s+table",
    r"delete\s+from",
    r"begin_secret|api[_-]?key\s*=|password\s*=",
)


class ContentSafetyError(Exception):
    """Raised when content is not inert/safe for deployment."""


def assert_safe_content(text: str, *, max_bytes: int) -> None:
    if not text.strip():
        raise ContentSafetyError("empty content")
    if len(text.encode("utf-8")) > max_bytes:
        raise ContentSafetyError(f"content exceeds {max_bytes} bytes")
    lowered = text.lower()
    for pattern in _UNSAFE_PATTERNS:
        if re.search(pattern, lowered):
            raise ContentSafetyError("content contains an unsafe or non-inert pattern")


def assert_safe_mcp_uri(uri: str) -> None:
    if not uri.startswith(_RESERVED_MCP_SCHEME):
        raise ContentSafetyError("MCP resource URI must use the reserved deceptiforge:// scheme")
    for scheme in ("http://", "https://", "file://", "ssh://", "ftp://"):
        if scheme in uri.lower():
            raise ContentSafetyError("MCP resource URI must not reference a real endpoint")


def is_safe_content(text: str, *, max_bytes: int) -> bool:
    try:
        assert_safe_content(text, max_bytes=max_bytes)
    except ContentSafetyError:
        return False
    return True
