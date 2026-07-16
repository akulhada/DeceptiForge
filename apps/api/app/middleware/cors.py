# Purpose: configure cross-origin access. Responsibilities: allow only explicitly configured browser origins. Future modules: add stricter per-environment policy when a browser client is introduced.
from collections.abc import Sequence

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware


def configure_cors(application: FastAPI, origins: Sequence[str]) -> None:
    """Attach CORS middleware only when an allow-list is configured."""
    if origins:
        application.add_middleware(CORSMiddleware, allow_origins=list(origins), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
