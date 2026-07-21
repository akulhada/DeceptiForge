# Purpose: provide the API route registry.
# Responsibilities: compose feature routers into one entrypoint, mounting demo routes only in
#   development with demo mode enabled. Future modules: include versioned routers as bounded
#   contexts are added.
from fastapi import APIRouter

from app.api.admin import router as admin_router
from app.api.agent_sensor import router as agent_sensor_router
from app.api.ai_tripwire import router as ai_tripwire_router
from app.api.analysis import router as analysis_router
from app.api.browser_sensor import router as browser_sensor_router
from app.api.capacity import router as capacity_router
from app.api.coverage import router as coverage_router
from app.api.database_honey import router as database_honey_router
from app.api.demo import router as demo_router
from app.api.deployments import router as deployments_router
from app.api.health import router as health_router
from app.api.integrations import router as integrations_router
from app.api.learning import router as learning_router
from app.api.narrative import router as narrative_router
from app.api.onboarding import router as onboarding_router
from app.api.pipeline import router as pipeline_router
from app.api.reliability import router as reliability_router
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
    router.include_router(capacity_router)
    router.include_router(admin_router)
    router.include_router(reliability_router)
    # Interactive Demo Lab: deterministic, stateless preview analysis. A core product route, always
    # mounted, authenticated + org-scoped (analysis:preview) — never under the /demo namespace.
    router.include_router(analysis_router)
    # Controlled learning mounts only when explicitly enabled; it never activates weights itself.
    if settings.learning_enabled:
        router.include_router(learning_router)
    # Decoy deployment routes mount only when the feature is explicitly enabled.
    if settings.decoy_deployment_enabled:
        router.include_router(deployments_router)
    if settings.database_connectors_enabled or settings.database_honey_deployment_enabled:
        router.include_router(database_honey_router)
    if (
        settings.rag_connectors_enabled
        or settings.mcp_connectors_enabled
        or settings.ai_tripwire_deployment_enabled
    ):
        router.include_router(ai_tripwire_router)
    if settings.browser_sensor_enabled:
        router.include_router(browser_sensor_router)
    if settings.agent_sensor_enabled:
        router.include_router(agent_sensor_router)
    if settings.coverage_engine_enabled:
        router.include_router(coverage_router)
    if settings.security_integrations_enabled:
        router.include_router(integrations_router)
    if settings.onboarding_enabled:
        router.include_router(onboarding_router)
    if settings.demo_enabled and settings.is_development:
        router.include_router(demo_router)
    return router
