# Purpose: reusable FastAPI dependencies.
# Responsibilities: provide a request-scoped database session that commits on success and rolls
#   back on error. Future modules: add authentication and tenant-scoping dependencies when needed.
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.database.session import get_sessionmaker


def get_db() -> Iterator[Session]:
    """Yield a session, committing on success and rolling back on failure."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
