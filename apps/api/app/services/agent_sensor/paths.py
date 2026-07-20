# Purpose: safe, deterministic normalization of agent-reported repository paths.
# Responsibilities: decode and canonicalize a raw path to a bounded repo-relative POSIX path, or
#   reject it. Defends against path traversal, encoded traversal, backslash/case tricks, absolute
#   paths, null bytes, and repository-root confusion so policy checks cannot be bypassed. Pure.
from __future__ import annotations

import posixpath
from fnmatch import fnmatch
from urllib.parse import unquote

_MAX_LEN = 2048
_MAX_DECODE_ROUNDS = 3


def normalize_path(raw: str) -> str | None:
    """Return a safe repo-relative POSIX path, or None if the path is unsafe/rejectable.

    Rejects: null bytes, over-long input, and anything that escapes the repository root after
    decoding + normalization (traversal). Case is preserved for storage; classification is
    case-insensitive elsewhere.
    """
    if not raw or "\x00" in raw or len(raw) > _MAX_LEN:
        return None
    value = raw
    # Repeatedly percent-decode (bounded) so %2e%2e/ style encoded traversal is caught.
    for _ in range(_MAX_DECODE_ROUNDS):
        decoded = unquote(value)
        if decoded == value:
            break
        value = decoded
    if "\x00" in value:
        return None
    value = value.replace("\\", "/")
    # Reject absolute paths (outside the repository root) and Windows drive paths.
    if value.startswith("/"):
        return None
    if len(value) >= 2 and value[1] == ":":
        return None
    # Strip leading './' segments; the path must be repo-relative.
    while value.startswith("./"):
        value = value[2:]
    normalized = posixpath.normpath(value)
    if normalized in (".", ""):
        return None
    # After normalization, any remaining leading .. means the path escapes the root.
    if normalized == ".." or normalized.startswith("../") or "/../" in f"/{normalized}":
        return None
    if normalized.startswith("/"):
        return None
    return normalized


def path_matches(pattern: str, path: str) -> bool:
    """Case-insensitive glob match of a normalized path against a policy pattern.

    A trailing '/**' (or bare directory prefix) matches the directory and everything under it.
    """
    p = normalize_path(pattern) or pattern.strip().replace("\\", "/").lstrip("/")
    p = p.lower().rstrip("/")
    target = path.lower()
    if p.endswith("/**"):
        base = p[:-3]
        return target == base or target.startswith(base + "/")
    if "*" in p or "?" in p:
        return fnmatch(target, p) or fnmatch(target, p + "/*")
    return target == p or target.startswith(p + "/")
