# Purpose: shared runtime for standalone lifecycle jobs.
# Responsibilities: provide a committed/rolled-back job session, a best-effort distributed advisory
#   lock (PostgreSQL) so concurrent cron invocations do not collide, and structured logging that
#   never emits secrets or payloads. Dependencies: settings, the session factory.
from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.session import get_sessionmaker

_logger = logging.getLogger("deceptiforge.jobs")


@contextmanager
def job_session() -> Iterator[Session]:
    """Yield a session that commits on success and rolls back on error."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def advisory_lock(session: Session, key: int) -> Iterator[bool]:
    """Best-effort cross-process lock. On PostgreSQL uses pg_try_advisory_lock; elsewhere a no-op.

    Yields whether the lock was acquired. A job that does not acquire it should exit without work so
    two concurrent workers never process the same rows.
    """
    dialect = session.bind.dialect.name if session.bind is not None else ""
    if dialect != "postgresql":
        yield True
        return
    acquired = bool(session.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}).scalar())
    try:
        yield acquired
    finally:
        if acquired:
            session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})


def log_event(event: str, **fields: object) -> None:
    """Emit a structured job log line (safe fields only)."""
    _logger.info(event, extra={"event": event, **fields})
