"""Establish the M0 migration baseline without domain tables.

Revision ID: 20260929_0001
Revises:
Create Date: 2026-09-29
"""

revision: str = "20260929_0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create only Alembic's own version marker in M0."""


def downgrade() -> None:
    """Return to the pre-baseline state."""
