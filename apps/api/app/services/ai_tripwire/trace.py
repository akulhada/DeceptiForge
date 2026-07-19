# Purpose: design traces that remain detectable after chunking, embedding, retrieval, excerpting,
#   summarization, or partial copying.
# Responsibilities: generate a high-entropy synthetic trace token, describe the trace mechanisms,
#   embed the token repeatedly through benign prose so any reasonable chunk carries it, and detect a
#   trace in text or metadata. Deterministic given a token. No model access.
from __future__ import annotations

import re
import secrets

_TOKEN_PREFIX = "DFAI"
# Insert the token at least this often (chars) so any chunk larger than this carries it.
_TOKEN_INTERVAL = 400
_METADATA_KEY = "deceptiforge_trace"


def generate_trace_token() -> str:
    """A high-entropy synthetic token; keeps substring-match false positives negligible."""
    return f"{_TOKEN_PREFIX}-{secrets.token_hex(6)}"


def metadata_key() -> str:
    return _METADATA_KEY


def reserved_phrase(token: str) -> str:
    """A benign, clearly-synthetic sentence that carries the token for phrase/marker detection."""
    return (
        f"DeceptiForge synthetic reference marker {token}. This is a decoy record for internal "
        "detection only; it contains no real data and requires no action."
    )


def embed_trace(body: str, token: str) -> str:
    """Re-emit the token through the body so it survives chunking and partial copying."""
    sentences = re.split(r"(?<=[.!?])\s+", body.strip())
    out: list[str] = [reserved_phrase(token)]
    running = 0
    for sentence in sentences:
        out.append(sentence)
        running += len(sentence)
        if running >= _TOKEN_INTERVAL:
            out.append(f"(ref {token})")
            running = 0
    out.append(reserved_phrase(token))
    return " ".join(part for part in out if part)


def trace_mechanisms(token: str, document_id: str) -> tuple[str, ...]:
    return (
        f"explicit synthetic token '{token}' repeated through the body",
        f"stable document id '{document_id}'",
        f"structured metadata field '{_METADATA_KEY}'",
        "reserved phrase embedded in benign prose",
    )


def detect_in_text(text: str, token: str) -> bool:
    """True if the token appears anywhere in the text (case-insensitive substring)."""
    return token.lower() in text.lower()


def detect_in_metadata(metadata: dict[str, str], token: str) -> bool:
    return metadata.get(_METADATA_KEY, "") == token or any(token in v for v in metadata.values())


def simulate_chunks(text: str, chunk_size: int = 512) -> list[str]:
    """Split text into fixed-size chunks (a coarse embedding-pipeline simulation)."""
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)] or [""]
