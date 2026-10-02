"""Seed the fixed, idempotent public-demo dataset through M1B.2."""

from gtm_state_api.database import get_session_factory
from gtm_state_api.demo_seed import seed_demo


def main() -> None:
    """Seed the synthetic workspace outside Alembic migrations."""

    with get_session_factory()() as session:
        seed_demo(session)
    print("Seeded Northstar Revenue Systems Demo M1B.2 snapshot.")


if __name__ == "__main__":
    main()
