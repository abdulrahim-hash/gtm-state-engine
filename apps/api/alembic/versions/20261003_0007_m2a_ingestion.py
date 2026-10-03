"""M2A provider-neutral source observations, normalization, and Evidence provenance.

Revision ID: 20261003_0007
Revises: 20261003_0006
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261003_0007"
down_revision: str | None = "20261003_0006"
branch_labels: str | None = None
depends_on: str | None = None

row_outcome = postgresql.ENUM(
    "ACCEPTED",
    "REJECTED",
    "UNRESOLVED",
    "DUPLICATE",
    name="ingestion_row_outcome",
    create_type=False,
)
normalization_outcome = postgresql.ENUM(
    "ACCEPTED",
    "REJECTED",
    "UNRESOLVED",
    "CONFLICT",
    name="normalization_outcome",
    create_type=False,
)
ingestion_reason = postgresql.ENUM(
    "INVALID_ROW",
    "INVALID_DATE",
    "INVALID_ASSERTION",
    "INVALID_CITATION",
    "FIELD_TOO_LARGE",
    "UNSUPPORTED_FACT",
    "EVENT_TIME_REQUIRED",
    "MISSING_IDENTITY",
    "AMBIGUOUS_IDENTITY",
    "SOURCE_ID_CONFLICT",
    "SOURCE_RECORD_CONFLICT",
    "DUPLICATE_OBSERVATION",
    name="ingestion_reason",
    create_type=False,
)
supersession_reason = postgresql.ENUM(
    "MAPPER_VERSION_PROMOTION",
    "IDENTITY_RULE_PROMOTION",
    name="evidence_supersession_reason",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    row_outcome.create(bind, checkfirst=True)
    normalization_outcome.create(bind, checkfirst=True)
    ingestion_reason.create(bind, checkfirst=True)
    supersession_reason.create(bind, checkfirst=True)
    op.alter_column("accounts", "segment", existing_type=sa.String(160), nullable=True)

    op.create_table(
        "ingestion_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system_key", sa.String(80), nullable=False),
        sa.Column("dataset_key", sa.String(80), nullable=False),
        sa.Column("schema_key", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("mapper_key", sa.String(80), nullable=False),
        sa.Column("mapper_version", sa.String(32), nullable=False),
        sa.Column("identity_rule_version", sa.String(32), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expected_rows", sa.Integer(), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("id", "workspace_id", name="uq_ingestion_batches_scope"),
        sa.UniqueConstraint(
            "id",
            "workspace_id",
            "source_system_key",
            "dataset_key",
            name="uq_ingestion_batches_source_scope",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "source_system_key",
            "dataset_key",
            "schema_key",
            "schema_version",
            "file_sha256",
            name="uq_ingestion_batches_semantic",
        ),
        sa.CheckConstraint("expected_rows BETWEEN 1 AND 500", name="ck_ingestion_batches_rows"),
        sa.CheckConstraint("file_sha256 ~ '^[a-f0-9]{64}$'", name="ck_ingestion_batches_hash"),
    )
    op.create_table(
        "source_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system_key", sa.String(80), nullable=False),
        sa.Column("dataset_key", sa.String(80), nullable=False),
        sa.Column("external_record_id", sa.String(120), nullable=False),
        sa.Column("external_account_id", sa.String(120), nullable=True),
        sa.Column("source_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("original_fields", postgresql.JSONB(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("first_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("first_row_ordinal", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["first_batch_id", "workspace_id", "source_system_key", "dataset_key"],
            [
                "ingestion_batches.id",
                "ingestion_batches.workspace_id",
                "ingestion_batches.source_system_key",
                "ingestion_batches.dataset_key",
            ],
            name="fk_source_observations_first_batch_scope",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "workspace_id", name="uq_source_observations_scope"),
        sa.UniqueConstraint(
            "id",
            "workspace_id",
            "source_system_key",
            "dataset_key",
            name="uq_source_observations_source_scope",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "source_system_key",
            "dataset_key",
            "external_record_id",
            "source_observed_at",
            "payload_sha256",
            name="uq_source_observations_semantic",
        ),
        sa.CheckConstraint("payload_sha256 ~ '^[a-f0-9]{64}$'", name="ck_source_observations_hash"),
        sa.CheckConstraint(
            "jsonb_typeof(original_fields) = 'object' "
            "AND octet_length(original_fields::text) <= 4096",
            name="ck_source_observations_fields",
        ),
        sa.CheckConstraint("first_row_ordinal > 0", name="ck_source_observations_ordinal"),
    )
    op.create_index(
        "ix_source_observations_record_time",
        "source_observations",
        [
            "workspace_id",
            "source_system_key",
            "dataset_key",
            "external_record_id",
            "source_observed_at",
        ],
    )
    op.create_table(
        "account_source_ids",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system_key", sa.String(80), nullable=False),
        sa.Column("dataset_key", sa.String(80), nullable=False),
        sa.Column("external_account_id", sa.String(120), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("origin_observation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id", "workspace_id"],
            ["accounts.id", "accounts.workspace_id"],
            name="fk_account_source_ids_account_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["origin_observation_id", "workspace_id", "source_system_key", "dataset_key"],
            [
                "source_observations.id",
                "source_observations.workspace_id",
                "source_observations.source_system_key",
                "source_observations.dataset_key",
            ],
            name="fk_account_source_ids_origin_scope",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "source_system_key",
            "dataset_key",
            "external_account_id",
            name="uq_account_source_ids_external",
        ),
    )
    op.create_table(
        "normalization_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_observation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mapper_key", sa.String(80), nullable=False),
        sa.Column("mapper_version", sa.String(32), nullable=False),
        sa.Column("identity_rule_version", sa.String(32), nullable=False),
        sa.Column("output_schema_version", sa.String(32), nullable=False),
        sa.Column("outcome", normalization_outcome, nullable=False),
        sa.Column("reason_code", ingestion_reason, nullable=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("fact_key", sa.String(160), nullable=True),
        sa.Column("fact_assertion", sa.String(16), nullable=True),
        sa.Column("evidence_classification", sa.String(16), nullable=True),
        sa.Column("normalized_fact", sa.String(500), nullable=True),
        sa.Column("fact_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("output_sha256", sa.String(64), nullable=True),
        sa.Column("resolution_input_sha256", sa.String(64), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_observation_id", "workspace_id"],
            ["source_observations.id", "source_observations.workspace_id"],
            name="fk_normalization_results_observation_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "workspace_id"],
            ["accounts.id", "accounts.workspace_id"],
            name="fk_normalization_results_account_scope",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "source_observation_id",
            "mapper_key",
            "mapper_version",
            "identity_rule_version",
            name="uq_normalization_results_version",
        ),
        sa.UniqueConstraint("id", "account_id", name="uq_normalization_results_evidence_scope"),
        sa.CheckConstraint(
            "output_sha256 IS NULL OR output_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_normalization_results_hash",
        ),
        sa.CheckConstraint(
            "resolution_input_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_normalization_results_resolution_hash",
        ),
        sa.CheckConstraint(
            "(outcome = 'ACCEPTED' AND account_id IS NOT NULL AND fact_key IS NOT NULL "
            "AND fact_assertion IS NOT NULL AND evidence_classification IS NOT NULL "
            "AND normalized_fact IS NOT NULL "
            "AND fact_observed_at IS NOT NULL AND output_sha256 IS NOT NULL "
            "AND reason_code IS NULL) "
            "OR (outcome <> 'ACCEPTED' AND reason_code IS NOT NULL "
            "AND output_sha256 IS NULL AND evidence_classification IS NULL)",
            name="ck_normalization_results_outcome_shape",
        ),
    )
    op.create_table(
        "ingestion_batch_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("row_sha256", sa.String(64), nullable=False),
        sa.Column("outcome", row_outcome, nullable=False),
        sa.Column("reason_code", ingestion_reason, nullable=True),
        sa.Column("source_observation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("normalization_result_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["ingestion_batches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_observation_id"], ["source_observations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["normalization_result_id"], ["normalization_results.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("batch_id", "ordinal", name="uq_ingestion_batch_rows_ordinal"),
        sa.CheckConstraint("ordinal > 0", name="ck_ingestion_batch_rows_ordinal"),
        sa.CheckConstraint("row_sha256 ~ '^[a-f0-9]{64}$'", name="ck_ingestion_batch_rows_hash"),
        sa.CheckConstraint(
            "(outcome = 'ACCEPTED' AND normalization_result_id IS NOT NULL "
            "AND reason_code IS NULL) "
            "OR (outcome <> 'ACCEPTED' AND reason_code IS NOT NULL)",
            name="ck_ingestion_batch_rows_outcome_shape",
        ),
    )
    op.create_index(
        "ix_ingestion_batch_rows_batch", "ingestion_batch_rows", ["batch_id", "ordinal"]
    )

    op.add_column(
        "evidence",
        sa.Column("normalization_result_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_evidence_normalization_account",
        "evidence",
        "normalization_results",
        ["normalization_result_id", "account_id"],
        ["id", "account_id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_evidence_normalization_result",
        "evidence",
        ["normalization_result_id"],
    )
    op.create_table(
        "evidence_supersessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("old_evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("new_evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", supersession_reason, nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["old_evidence_id"], ["evidence.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["new_evidence_id"], ["evidence.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("old_evidence_id", name="uq_evidence_supersessions_old"),
        sa.UniqueConstraint("new_evidence_id", name="uq_evidence_supersessions_new"),
        sa.CheckConstraint(
            "old_evidence_id <> new_evidence_id", name="ck_evidence_supersessions_distinct"
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM ingestion_batches)")):
        raise RuntimeError(
            "M2A downgrade requires removal of imported batches through an explicit data procedure"
        )
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM accounts WHERE segment IS NULL)")):
        raise RuntimeError("M2A downgrade cannot represent accounts with null segment under M1D")
    op.drop_table("evidence_supersessions")
    op.drop_constraint("uq_evidence_normalization_result", "evidence", type_="unique")
    op.drop_constraint("fk_evidence_normalization_account", "evidence", type_="foreignkey")
    op.drop_column("evidence", "normalization_result_id")
    op.drop_index("ix_ingestion_batch_rows_batch", table_name="ingestion_batch_rows")
    op.drop_table("ingestion_batch_rows")
    op.drop_table("normalization_results")
    op.drop_table("account_source_ids")
    op.drop_index("ix_source_observations_record_time", table_name="source_observations")
    op.drop_table("source_observations")
    op.drop_table("ingestion_batches")
    op.alter_column("accounts", "segment", existing_type=sa.String(160), nullable=False)
    supersession_reason.drop(bind, checkfirst=True)
    ingestion_reason.drop(bind, checkfirst=True)
    normalization_outcome.drop(bind, checkfirst=True)
    row_outcome.drop(bind, checkfirst=True)
