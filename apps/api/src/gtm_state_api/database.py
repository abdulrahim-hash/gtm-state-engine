"""Synchronous PostgreSQL access for the initial service boundary."""

from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from gtm_state_api.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Create a process-local SQLAlchemy 2.x engine using psycopg 3."""

    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
    )


def database_is_ready(engine: Engine | None = None) -> bool:
    """Return whether PostgreSQL accepts a minimal query."""

    candidate = engine or get_engine()
    try:
        with candidate.connect() as connection:
            return connection.execute(text("SELECT 1")).scalar_one() == 1
    except SQLAlchemyError:
        return False
