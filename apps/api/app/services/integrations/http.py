# Purpose: the real HTTP transport for deliveries (httpx), with SSRF-hardening defaults.
# Responsibilities: send one request with redirects disabled, a strict timeout, and a capped
#   response snippet; translate network failures into TransportError. Redirects are never followed
#   (an open redirect could bypass SSRF validation). The factory is monkeypatched in tests.
# Dependencies: httpx, adapter contract.
from __future__ import annotations

import httpx

from app.services.integrations.adapter import (
    HttpRequest,
    HttpResponse,
    HttpTransport,
    TransportError,
)

_MAX_SNIPPET = 512


class HttpxTransport:
    def send(self, request: HttpRequest, *, timeout: float) -> HttpResponse:
        try:
            with httpx.Client(follow_redirects=False, timeout=timeout) as client:
                response = client.request(
                    request.method, request.url, content=request.body, headers=request.headers
                )
        except httpx.HTTPError as error:
            raise TransportError("delivery transport failure") from error
        return HttpResponse(
            status=response.status_code,
            headers={k.lower(): v for k, v in response.headers.items()},
            body_snippet=response.text[:_MAX_SNIPPET],
        )


def build_http_transport() -> HttpTransport:
    """Return the production transport. Tests monkeypatch this to an in-memory fake."""
    return HttpxTransport()
