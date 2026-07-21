# Purpose: configure cross-origin access safely.
# Responsibilities: attach CORS only for an explicit allow-list, never combine credentials with a
#   wildcard origin, and restrict methods and headers. Fail closed when no origins are configured.
# Dependencies: FastAPI and Starlette CORS middleware.
from collections.abc import Sequence

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

# CORS is scoped to what a BROWSER PAGE actually sends — verified against the dashboard clients:
#   GET/POST            general reads and creates
#   PUT                 policy updates (PUT /browser-ai-policy, PUT /agent-scope-policies/{id})
#   DELETE              policy removal (DELETE /agent-scope-policies/{id})
# PATCH is absent because no route accepts it and no client sends it.
_ALLOWED_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]

# Only the headers the dashboard sends. Signed-ingestion headers (monitor id, signature, nonce,
# timestamp) are deliberately ABSENT: signed monitoring is produced by server-side senders and by
# the MV3 extension, which uses host_permissions and therefore does not go through page CORS.
# Advertising signing headers here would hand browser-origin pages a capability they must not have.
_ALLOWED_HEADERS = [
    "content-type",
    "x-deceptiforge-api-key",
    "x-deceptiforge-org-id",
]


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
