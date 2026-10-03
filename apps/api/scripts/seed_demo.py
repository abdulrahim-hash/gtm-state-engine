"""Seed the fixed, idempotent public-demo dataset through M1C."""

from gtm_state_api.database import get_session_factory
from gtm_state_api.demo_seed import seed_demo


def main() -> None:
    """Seed the synthetic workspace outside Alembic migrations."""

    with get_session_factory()() as session:
        seed_demo(session)
    print("Seeded Northstar Revenue Systems Demo through M1C.")


if __name__ == "__main__":
    main()
