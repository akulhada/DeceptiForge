# Purpose: provide the API route registry. Responsibilities: offer one composition point for future feature routers. Future modules: include versioned routers as bounded contexts are implemented.
from fastapi import APIRouter

api_router = APIRouter()
