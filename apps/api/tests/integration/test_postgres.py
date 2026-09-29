"""PostgreSQL integration tests run after migrations."""

import pytest
from sqlalchemy import inspect, text

from gtm_state_api.database import get_engine

pytestmark = pytest.mark.integration


def test_postgres_readiness_query() -> None:
    engine = get_engine()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1


def test_baseline_migration_is_applied() -> None:
    engine = get_engine()
    inspector = inspect(engine)

    assert "alembic_version" in inspector.get_table_names()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "20260929_0001"
        )
