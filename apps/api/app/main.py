# Purpose: construct the FastAPI application.
# Responsibilities: compose infrastructure middleware and the settings-derived route registry.
# Future modules: register versioned feature routers through build_api_router.
from fastapi import FastAPI

from app.config.settings import get_settings
from app.middleware.cors import configure_cors
from app.routes.router import build_api_router


def create_app() -> FastAPI:
    """Create the API without binding it to a deployment environment."""
    settings = get_settings()
    application = FastAPI(title=settings.app_name, debug=settings.is_development)
    configure_cors(application, settings.cors_origins)
    application.include_router(build_api_router(settings))
    return application


app = create_app()
