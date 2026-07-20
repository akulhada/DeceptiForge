# Purpose: add request correlation, a request-body size limit, and safe global error handling.
# Responsibilities: attach a request id to every request/response, reject oversized bodies early,
#   and convert unexpected errors into safe responses that never leak stack traces, filesystem
#   paths, SQL, provider details, or raw payloads. Dependencies: FastAPI/Starlette and logging.
from __future__ import annotations

import json
import logging
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_logger = logging.getLogger("deceptiforge")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id and expose it on the response for correlation."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("x-request-id") or uuid4().hex
        request.state.request_id = request_id
        response: Response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response


class BodyLimitMiddleware:
    """Reject oversized request bodies while streaming, without trusting Content-Length.

    This is a pure-ASGI middleware so it counts bytes as they arrive on ``receive``. The moment the
    running total exceeds the limit it sends a 413 itself, then feeds the downstream app an
    ``http.disconnect`` so it stops reading, and swallows anything the app then tries to send. A
    chunked or no-Content-Length request therefore cannot slip past and be buffered downstream; a
    declared Content-Length over the limit is rejected before the app is invoked at all.
    """

    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        self._app = app
        self._max = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        declared = _content_length(scope)
        if declared is not None and declared > self._max:
            await self._reject(scope, send)
            return

        total = 0
        rejected = False

        async def counting_receive() -> Message:
            nonlocal total, rejected
            if rejected:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self._max:
                    rejected = True
                    await self._reject(scope, send)
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            # Once we have sent the 413, suppress any response the app tries to produce.
            if rejected:
                return
            await send(message)

        await self._app(scope, counting_receive, guarded_send)

    async def _reject(self, scope: Scope, send: Send) -> None:
        request_id = _scope_request_id(scope)
        from app.services.metrics import emit

        emit("body_size_rejected", request_id=request_id, path=scope.get("path", ""))
        body = json.dumps({"detail": "request body too large", "request_id": request_id}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status.HTTP_413_CONTENT_TOO_LARGE,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"x-request-id", request_id.encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def _content_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", []):
        if name == b"content-length" and value.isdigit():
            return int(value)
    return None


def _scope_request_id(scope: Scope) -> str:
    for name, value in scope.get("headers", []):
        if name == b"x-request-id":
            return bytes(value).decode("latin-1")
    return uuid4().hex


def _request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else "unknown"


_SAFE_ERROR_HEADERS = frozenset({"retry-after", "www-authenticate"})


def _safe_response(
    request: Request, status_code: int, detail: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    request_id = _request_id(request)
    response_headers = {"x-request-id": request_id}
    response_headers.update(
        {
            key: value
            for key, value in (headers or {}).items()
            if key.lower() in _SAFE_ERROR_HEADERS
        }
    )
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail, "request_id": request_id},
        headers=response_headers,
    )


def register_exception_handlers(application: FastAPI) -> None:
    """Install handlers that return safe, correlated error responses."""

    @application.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _safe_response(request, exc.status_code, str(exc.detail), dict(exc.headers or {}))

    @application.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _safe_response(request, status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid request")

    @application.exception_handler(SQLAlchemyError)
    async def _database(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        _log(request, "database_error", exc)
        return _safe_response(
            request, status.HTTP_500_INTERNAL_SERVER_ERROR, "internal server error"
        )

    @application.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        _log(request, "unexpected_error", exc)
        return _safe_response(
            request, status.HTTP_500_INTERNAL_SERVER_ERROR, "internal server error"
        )


def _log(request: Request, error_class: str, exc: Exception) -> None:
    organization_id = request.headers.get("x-deceptiforge-org-id", "unknown")
    _logger.error(
        "request_error",
        extra={
            "request_id": _request_id(request),
            "organization_id": organization_id,
            "route": request.url.path,
            "error_class": error_class,
            "exception_type": type(exc).__name__,
        },
    )
