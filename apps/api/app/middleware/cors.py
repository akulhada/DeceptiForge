# Purpose: configure cross-origin access safely.
# Responsibilities: attach CORS only for an explicit allow-list, never combine credentials with a
#   wildcard origin, and restrict methods and headers. Fail closed when no origins are configured.
# Dependencies: FastAPI and Starlette CORS middleware.
from collections.abc import Sequence

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

_ALLOWED_METHODS = ["GET", "POST", "OPTIONS"]
_ALLOWED_HEADERS = ["content-type", "x-deceptiforge-api-key", "x-deceptiforge-org-id"]


def configure_cors(
    application: FastAPI, origins: Sequence[str], *, allow_credentials: bool = False
) -> None:
    """Attach CORS only when a non-wildcard allow-list is configured.

    With no configured origins CORS stays off (fail closed). A wildcard origin is refused when
    credentials are allowed, since that combination is unsafe.
    """
    origin_list = [origin for origin in origins if origin]
    if not origin_list:
        return
    if "*" in origin_list:
        raise ValueError("CORS wildcard origins are not allowed; configure an explicit allow-list")

    application.add_middleware(
        CORSMiddleware,
        allow_origins=origin_list,
        allow_credentials=allow_credentials,
        allow_methods=_ALLOWED_METHODS,
        allow_headers=_ALLOWED_HEADERS,
    )
