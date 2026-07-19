# Purpose: provide the API route registry.
# Responsibilities: compose feature routers into one entrypoint, mounting demo routes only in
#   development with demo mode enabled. Future modules: include versioned routers as bounded
#   contexts are added.
from fastapi import APIRouter

from app.api.admin import router as admin_router
from app.api.demo import router as demo_router
from app.api.deployments import router as deployments_router
from app.api.health import router as health_router
from app.api.narrative import router as narrative_router
from app.api.pipeline import router as pipeline_router
from app.api.tenant import router as tenant_router
from app.config.settings import Settings


def build_api_router(settings: Settings) -> APIRouter:
    """Compose the API router; demo routes mount only when DEMO_ENABLED and APP_ENV=development.

    Requiring both an explicit flag and a development environment means demo routes can never be
    exposed on a production-like deployment, even if DEMO_ENABLED is set to true.
    """
    router = APIRouter()
    router.include_router(health_router)
    router.include_router(pipeline_router)
    router.include_router(narrative_router)
    router.include_router(tenant_router)
    router.include_router(admin_router)
    # Decoy deployment routes mount only when the feature is explicitly enabled.
    if settings.decoy_deployment_enabled:
        router.include_router(deployments_router)
    if settings.demo_enabled and settings.is_development:
        router.include_router(demo_router)
    return router
