"""PostgreSQL integration tests run after migrations."""

import pytest
from sqlalchemy import inspect, text

from gtm_state_api.database import get_engine

pytestmark = pytest.mark.integration


def test_postgres_readiness_query() -> None:
    engine = get_engine()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1


def test_m2c_migration_is_applied() -> None:
    engine = get_engine()
    inspector = inspect(engine)

    assert "alembic_version" in inspector.get_table_names()
    assert "source_read_runs" in inspector.get_table_names()
    run_columns = {item["name"] for item in inspector.get_columns("source_read_runs")}
    assert {"workspace_id", "scope_sha256", "request_sha256", "observation_id"} <= run_columns
    observation_columns = {item["name"] for item in inspector.get_columns("source_observations")}
    assert {"first_batch_id", "source_read_run_id"} <= observation_columns
    checks = {item["name"] for item in inspector.get_check_constraints("source_observations")}
    assert "ck_source_observations_one_origin" in checks
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "20261006_0009"
        )
