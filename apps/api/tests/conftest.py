# Purpose: configure API tests with an isolated in-memory database and per-test settings.
# Responsibilities: satisfy settings validation, bind SQLAlchemy to SQLite, override the
#   request-scoped session, and build the app under a chosen DEMO_ENABLED/APP_ENV so gating and
#   scan-hardening can be exercised. Dependencies: FastAPI test client.
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/deceptiforge")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import get_settings
from app.database.base import Base
from app.dependencies import get_db
from app.models import records as _records  # noqa: F401  (register tables)


@contextmanager
def build_client(
    *,
    demo_enabled: bool = True,
    app_env: str = "development",
    auth_enabled: bool = False,
    demo_api_key: str = "local-development-key",
    api_key_bindings: str = "{}",
    cors_origins: str | None = None,
    cors_allow_credentials: bool = False,
) -> Iterator[TestClient]:
    overrides = {
        "DEMO_ENABLED": "true" if demo_enabled else "false",
        "APP_ENV": app_env,
        "AUTH_ENABLED": "true" if auth_enabled else "false",
        "DEMO_API_KEY": demo_api_key,
        "API_KEY_BINDINGS": api_key_bindings,
        "CORS_ORIGINS": cors_origins if cors_origins is not None else "[]",
        "CORS_ALLOW_CREDENTIALS": "true" if cors_allow_credentials else "false",
    }
    previous = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    get_settings.cache_clear()
    from app.services.rate_limit import rate_limiter

    rate_limiter.clear()

    from app.main import create_app

    application = create_app()
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db() -> Iterator[Session]:
        session = testing_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    application.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(application) as test_client:
            yield test_client
    finally:
        application.dependency_overrides.clear()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with build_client(demo_enabled=True) as test_client:
        yield test_client


@pytest.fixture
def make_client():
    """Factory for building a client under specific settings (as a context manager)."""
    return build_client
