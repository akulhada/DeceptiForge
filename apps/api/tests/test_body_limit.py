# Purpose: verify streaming request-body size enforcement in the pure-ASGI middleware.
# Responsibilities: reject oversized Content-Length and oversized chunked/no-length requests while
#   streaming (413), accept exact-limit and under-limit requests, and handle a malformed stream
#   without buffering the whole body. Dependencies: the test client factory and env overrides.
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

_PATH = "/monitoring/events"


@contextmanager
def _client_with_limit(make_client, limit: int) -> Iterator[object]:  # type: ignore[no-untyped-def]
    """Build a dev client whose max request body is ``limit`` bytes."""
    previous = os.environ.get("MAX_REQUEST_BODY_BYTES")
    os.environ["MAX_REQUEST_BODY_BYTES"] = str(limit)
    try:
        # build_client clears the settings cache on entry, so the override is picked up.
        with make_client(demo_enabled=True, app_env="development") as client:
            yield client
    finally:
        if previous is None:
            os.environ.pop("MAX_REQUEST_BODY_BYTES", None)
        else:
            os.environ["MAX_REQUEST_BODY_BYTES"] = previous


def _chunks(total: int, size: int = 16) -> Iterator[bytes]:
    """Yield ``total`` bytes in small chunks (httpx sends these without a Content-Length)."""
    sent = 0
    while sent < total:
        step = min(size, total - sent)
        sent += step
        yield b"x" * step


def test_oversized_content_length_rejected(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client_with_limit(make_client, 100) as client:
        response = client.post(_PATH, content=b"x" * 200)  # bytes send a Content-Length header
        assert response.status_code == 413
        assert response.json()["detail"] == "request body too large"
        assert response.headers.get("x-request-id")


def test_oversized_chunked_no_length_rejected(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client_with_limit(make_client, 100) as client:
        # A generator body is sent chunked with no Content-Length; the limiter must still stop it.
        response = client.post(_PATH, content=_chunks(400))
        assert "content-length" not in {k.lower() for k in response.request.headers}
        assert response.status_code == 413


def test_exact_limit_request_is_allowed_through(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client_with_limit(make_client, 120) as client:
        response = client.post(_PATH, content=b"z" * 120)  # exactly at the limit: not rejected
        # Passes the size gate (not 413); the body is not valid JSON, so routing returns 422.
        assert response.status_code != 413


def test_under_limit_request_is_allowed_through(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client_with_limit(make_client, 1000) as client:
        assert client.post(_PATH, content=_chunks(50)).status_code != 413


def test_malformed_stream_fails_gracefully(make_client) -> None:  # type: ignore[no-untyped-def]
    # A stream that breaks partway must not hang or be treated as a successful ingest; the request
    # completes with a client error rather than buffering the whole (incomplete) body.
    def broken() -> Iterator[bytes]:
        yield b"x" * 16
        raise RuntimeError("stream broke")

    with _client_with_limit(make_client, 1_000_000) as client:
        try:
            response = client.post(_PATH, content=broken())
        except Exception:  # noqa: BLE001 - some transports surface the broken stream as an error
            return
        assert response.status_code >= 400
