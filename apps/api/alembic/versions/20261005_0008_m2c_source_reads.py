"""M2C local private source read runs and alternative observation provenance.

Revision ID: 20261005_0008
Revises: 20261003_0007
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261005_0008"
down_revision: str | None = "20261003_0007"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "source_read_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system_key", sa.String(80), nullable=False),
        sa.Column("dataset_key", sa.String(80), nullable=False),
        sa.Column("adapter_key", sa.String(80), nullable=False),
        sa.Column("adapter_version", sa.String(32), nullable=False),
        sa.Column("mapping_version", sa.String(32), nullable=False),
        sa.Column("scope_sha256", sa.String(64), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("response_sha256", sa.String(64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("accepted_count", sa.Integer(), nullable=False),
        sa.Column("unresolved_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("failure_code", sa.String(40), nullable=True),
        sa.Column("provider_correlation_id", sa.String(120), nullable=True),
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["observation_id"], ["source_observations.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "id",
            "workspace_id",
            "source_system_key",
            "dataset_key",
            name="uq_source_read_runs_scope",
        ),
        sa.CheckConstraint(
            "scope_sha256 ~ '^[a-f0-9]{64}$'", name="ck_source_read_runs_scope_hash"
        ),
        sa.CheckConstraint(
            "request_sha256 ~ '^[a-f0-9]{64}$'", name="ck_source_read_runs_request_hash"
        ),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'SUCCEEDED', 'NOT_FOUND', 'UNRESOLVED', "
            "'REJECTED', 'CONFLICT', 'FAILED')",
            name="ck_source_read_runs_status",
        ),
        sa.CheckConstraint(
            "accepted_count BETWEEN 0 AND 1 AND unresolved_count BETWEEN 0 AND 1 "
            "AND rejected_count BETWEEN 0 AND 1 AND retry_count BETWEEN 0 AND 2",
            name="ck_source_read_runs_counts",
        ),
    )
    op.alter_column(
        "source_observations",
        "first_batch_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.add_column(
        "source_observations",
        sa.Column("source_read_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_source_observations_read_run_scope",
        "source_observations",
        "source_read_runs",
        ["source_read_run_id", "workspace_id", "source_system_key", "dataset_key"],
        ["id", "workspace_id", "source_system_key", "dataset_key"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_source_observations_one_origin",
        "source_observations",
        "(first_batch_id IS NOT NULL) <> (source_read_run_id IS NOT NULL)",
    )


def downgrade() -> None:
    bind = op.get_bind()
    run_count = bind.scalar(sa.text("SELECT count(*) FROM source_read_runs"))
    if run_count:
        raise RuntimeError(
            "M2C source-read runs exist; downgrade would destroy provider provenance"
        )
    op.drop_constraint("ck_source_observations_one_origin", "source_observations", type_="check")
    op.drop_constraint(
        "fk_source_observations_read_run_scope", "source_observations", type_="foreignkey"
    )
    op.drop_column("source_observations", "source_read_run_id")
    op.alter_column(
        "source_observations",
        "first_batch_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.drop_table("source_read_runs")
