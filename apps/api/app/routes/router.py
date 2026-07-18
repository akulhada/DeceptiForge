# Purpose: provide the API route registry.
# Responsibilities: compose feature routers into one entrypoint, mounting demo routes only when
#   explicitly enabled. Future modules: include versioned routers as bounded contexts are added.
from fastapi import APIRouter

from app.api.demo import router as demo_router
from app.api.pipeline import router as pipeline_router
from app.config.settings import Settings


def build_api_router(settings: Settings) -> APIRouter:
    """Compose the API router; demo routes are mounted only when DEMO_ENABLED is true.

    Gating on an explicit flag (not APP_ENV) prevents accidental exposure of demo endpoints
    through environment-name confusion.
    """
    router = APIRouter()
    router.include_router(pipeline_router)
    if settings.demo_enabled:
        router.include_router(demo_router)
    return router
