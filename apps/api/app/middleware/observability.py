# Purpose: add request correlation, a request-body size limit, and safe global error handling.
# Responsibilities: attach a request id to every request/response, reject oversized bodies early,
#   and convert unexpected errors into safe responses that never leak stack traces, filesystem
#   paths, SQL, provider details, or raw payloads. Dependencies: FastAPI/Starlette and logging.
from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

_logger = logging.getLogger("deceptiforge")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id and expose it on the response for correlation."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("x-request-id") or uuid4().hex
        request.state.request_id = request_id
        response: Response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response


class BodyLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose declared body exceeds the configured maximum."""

    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        super().__init__(app)
        self._max = max_body_bytes

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        content_length = request.headers.get("content-length")
        if (
            content_length is not None
            and content_length.isdigit()
            and int(content_length) > self._max
        ):
            return _safe_response(
                request, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "request body too large"
            )
        return await call_next(request)


def _request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else "unknown"


def _safe_response(request: Request, status_code: int, detail: str) -> JSONResponse:
    request_id = _request_id(request)
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail, "request_id": request_id},
        headers={"x-request-id": request_id},
    )


def register_exception_handlers(application: FastAPI) -> None:
    """Install handlers that return safe, correlated error responses."""

    @application.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _safe_response(request, exc.status_code, str(exc.detail))

    @application.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _safe_response(request, status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid request")

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
