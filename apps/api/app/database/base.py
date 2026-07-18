# Purpose: define shared SQLAlchemy declarative metadata. Responsibilities: provide the parent
# class for future persistence models. Future modules: domain models inherit Base and are imported
# for Alembic discovery.
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for future SQLAlchemy models."""
