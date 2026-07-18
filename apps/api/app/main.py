# Purpose: construct the FastAPI application.
# Responsibilities: compose infrastructure middleware (CORS, request context, body limit), safe
#   error handling, and the settings-derived route registry.
# Future modules: register versioned feature routers through build_api_router.
from fastapi import FastAPI

from app.config.settings import get_settings
from app.middleware.cors import configure_cors
from app.middleware.observability import (
    BodyLimitMiddleware,
    RequestContextMiddleware,
    register_exception_handlers,
)
from app.routes.router import build_api_router


def create_app() -> FastAPI:
    """Create the API without binding it to a deployment environment."""
    settings = get_settings()
    application = FastAPI(title=settings.app_name, debug=settings.is_development)
    configure_cors(
        application, settings.cors_origins, allow_credentials=settings.cors_allow_credentials
    )
    application.add_middleware(BodyLimitMiddleware, max_body_bytes=settings.max_request_body_bytes)
    application.add_middleware(RequestContextMiddleware)
    register_exception_handlers(application)
    application.include_router(build_api_router(settings))
    return application


app = create_app()
