# Purpose: provide the API route registry.
# Responsibilities: compose feature routers into one entrypoint mounted by the application.
# Future modules: include versioned routers as bounded contexts are implemented.
from fastapi import APIRouter

from app.api.pipeline import router as pipeline_router

api_router = APIRouter()
api_router.include_router(pipeline_router)
