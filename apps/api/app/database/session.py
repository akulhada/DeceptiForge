# Purpose: construct database engine and sessions lazily.
# Responsibilities: centralize connection pooling and the session factory without requiring a
#   configured database at import time (so tests can bind an alternate engine).
# Future modules: add request-scoped transaction handling in dependencies.
from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import get_settings


@lru_cache
def get_engine() -> Engine:
    """Build one process-wide engine from settings on first use."""
    return create_engine(get_settings().database_url.unicode_string(), pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    """Return a cached session factory bound to the settings engine."""
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
