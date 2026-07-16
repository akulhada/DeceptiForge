# Purpose: construct database engine and sessions. Responsibilities: centralize connection pooling and session factory behavior. Future modules: add request-scoped transaction handling in dependencies.
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings

engine = create_engine(get_settings().database_url.unicode_string(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
