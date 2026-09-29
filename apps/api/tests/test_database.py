"""Database boundary tests."""

from sqlalchemy import create_engine

from gtm_state_api.database import database_is_ready


def test_database_readiness_returns_false_for_unavailable_database() -> None:
    engine = create_engine(
        "postgresql+psycopg://invalid:invalid@127.0.0.1:1/unavailable",
        connect_args={"connect_timeout": 1},
    )

    assert database_is_ready(engine) is False
    engine.dispose()
