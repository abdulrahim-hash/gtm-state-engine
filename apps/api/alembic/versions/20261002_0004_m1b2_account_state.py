"""Add deterministic, provenance-backed account-state snapshots.

Revision ID: 20261002_0004
Revises: 20260930_0003
Create Date: 2026-10-02
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261002_0004"
down_revision: str | None = "20260930_0003"
branch_labels: str | None = None
depends_on: str | None = None

evidence_assertion = postgresql.ENUM(
    "PRESENT", "ABSENT", "INCONCLUSIVE", name="evidence_assertion", create_type=False
)
account_fit_context = postgresql.ENUM(
    "MATCH",
    "PARTIAL",
    "MISMATCH",
    "UNKNOWN",
    "INCONCLUSIVE",
    name="account_fit_context",
    create_type=False,
)
account_timing_state = postgresql.ENUM(
    "ACTIVE",
    "STALE",
    "NONE",
    "UNKNOWN",
    "INCONCLUSIVE",
    name="account_timing_state",
    create_type=False,
)
account_relationship_state = postgresql.ENUM(
    "EXISTING_RELATIONSHIP",
    "NO_EXISTING_RELATIONSHIP",
    "UNKNOWN",
    "INCONCLUSIVE",
    name="account_relationship_state",
    create_type=False,
)
account_evidence_sufficiency = postgresql.ENUM(
    "SUFFICIENT",
    "PARTIAL",
    "INSUFFICIENT",
    "CONTRADICTORY",
    name="account_evidence_sufficiency",
    create_type=False,
)
account_state_facet = postgresql.ENUM(
    "FIT_CONTEXT",
    "TIMING_STATE",
    "RELATIONSHIP_STATE",
    "EVIDENCE_SUFFICIENCY",
    name="account_state_facet",
    create_type=False,
)
fit_criterion_result = postgresql.ENUM(
    "MATCH",
    "MISMATCH",
    "UNKNOWN",
    "INCONCLUSIVE",
    name="fit_criterion_result",
    create_type=False,
)
account_state_reason_code = postgresql.ENUM(
    "ALL_REQUIRED_FIT_CRITERIA_MATCH",
    "FIT_CRITERION_MATCH",
    "SOME_REQUIRED_FIT_CRITERIA_MATCH",
    "REQUIRED_FIT_CRITERION_MISMATCH",
    "FIT_EVIDENCE_MISSING",
    "FIT_EVIDENCE_NOT_CURRENT",
    "FIT_EVIDENCE_AMBIGUOUS",
    "FIT_EVIDENCE_CONTRADICTORY",
    "CURRENT_SIGNAL_DETECTED",
    "STALE_SIGNAL_PRESENT",
    "ALL_SIGNAL_EVALUATIONS_NO_MATCH",
    "NO_ENABLED_SIGNAL_DEFINITIONS",
    "SIGNAL_EVALUATION_MISSING",
    "SIGNAL_EVIDENCE_MISSING",
    "SIGNAL_EVIDENCE_AMBIGUOUS",
    "SIGNAL_EVIDENCE_CONTRADICTORY",
    "EXISTING_RELATIONSHIP_PRESENT",
    "EXISTING_RELATIONSHIP_ABSENT",
    "RELATIONSHIP_EVIDENCE_MISSING",
    "RELATIONSHIP_EVIDENCE_NOT_CURRENT",
    "RELATIONSHIP_EVIDENCE_AMBIGUOUS",
    "RELATIONSHIP_EVIDENCE_CONTRADICTORY",
    "ALL_REQUIRED_STATE_INPUTS_SUPPORTED",
    "FIT_COVERAGE_INCOMPLETE",
    "TIMING_COVERAGE_INCOMPLETE",
    "RELATIONSHIP_COVERAGE_INCOMPLETE",
    "CONTRADICTORY_STATE_INPUTS",
    name="account_state_reason_code",
    create_type=False,
)


def upgrade() -> None:
    """Create M1B.2's immutable state history and normalized provenance."""

    account_fit_context.create(op.get_bind(), checkfirst=True)
    account_timing_state.create(op.get_bind(), checkfirst=True)
    account_relationship_state.create(op.get_bind(), checkfirst=True)
    account_evidence_sufficiency.create(op.get_bind(), checkfirst=True)
    account_state_facet.create(op.get_bind(), checkfirst=True)
    fit_criterion_result.create(op.get_bind(), checkfirst=True)
    account_state_reason_code.create(op.get_bind(), checkfirst=True)

    op.create_unique_constraint(
        "uq_evidence_id_strategy_version",
        "evidence",
        ["id", "strategy_version_id"],
    )
    op.create_table(
        "strategy_fit_criteria",
        sa.Column("fit_criterion_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stable_key", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("input_fact_key", sa.String(length=160), nullable=False),
        sa.Column("expected_assertion", evidence_assertion, nullable=False),
        sa.Column("source_strategy_evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_version_id", "workspace_id"],
            ["strategy_versions.id", "strategy_versions.workspace_id"],
            name="fk_strategy_fit_criteria_strategy_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_strategy_evidence_id", "strategy_version_id"],
            ["evidence.id", "evidence.strategy_version_id"],
            name="fk_strategy_fit_criteria_source_evidence",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "strategy_version_id",
            "stable_key",
            name="uq_strategy_fit_criteria_stable_key",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "strategy_version_id",
            "input_fact_key",
            name="uq_strategy_fit_criteria_fact_key",
        ),
        sa.UniqueConstraint(
            "fit_criterion_id",
            "workspace_id",
            "strategy_version_id",
            name="uq_strategy_fit_criteria_scope",
        ),
        sa.CheckConstraint(
            "stable_key ~ '^[a-z][a-z0-9_]*$'",
            name="ck_strategy_fit_criteria_stable_key",
        ),
        sa.CheckConstraint(
            "input_fact_key ~ '^[a-z][a-z0-9_.]*$'",
            name="ck_strategy_fit_criteria_input_fact_key",
        ),
        sa.CheckConstraint(
            "expected_assertion <> 'INCONCLUSIVE'",
            name="ck_strategy_fit_criteria_expected_assertion",
        ),
    )
    op.create_table(
        "account_state_snapshots",
        sa.Column("state_snapshot_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("state_engine_version", sa.String(length=32), nullable=False),
        sa.Column("fit_context", account_fit_context, nullable=False),
        sa.Column("timing_state", account_timing_state, nullable=False),
        sa.Column("relationship_state", account_relationship_state, nullable=False),
        sa.Column("evidence_sufficiency", account_evidence_sufficiency, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id", "workspace_id"],
            ["accounts.id", "accounts.workspace_id"],
            name="fk_account_state_snapshots_account_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["strategy_version_id", "workspace_id"],
            ["strategy_versions.id", "strategy_versions.workspace_id"],
            name="fk_account_state_snapshots_strategy_workspace",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "account_id",
            "strategy_version_id",
            "state_as_of",
            "state_engine_version",
            "input_hash",
            name="uq_account_state_snapshots_semantic_input",
        ),
        sa.UniqueConstraint(
            "state_snapshot_id",
            "account_id",
            name="uq_account_state_snapshots_id_account",
        ),
        sa.UniqueConstraint(
            "state_snapshot_id",
            "workspace_id",
            "account_id",
            "strategy_version_id",
            name="uq_account_state_snapshots_scope",
        ),
        sa.CheckConstraint(
            "input_hash ~ '^[a-f0-9]{64}$'",
            name="ck_account_state_snapshots_input_hash",
        ),
    )
    op.create_index(
        "ix_account_state_snapshots_current",
        "account_state_snapshots",
        [
            "workspace_id",
            "account_id",
            "strategy_version_id",
            "state_as_of",
            "computed_at",
        ],
    )
    op.create_table(
        "state_snapshot_reasons",
        sa.Column(
            "state_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "account_state_snapshots.state_snapshot_id",
                name="fk_state_snapshot_reasons_snapshot",
                ondelete="RESTRICT",
            ),
            primary_key=True,
        ),
        sa.Column("facet", account_state_facet, primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("reason_code", account_state_reason_code, nullable=False),
        sa.UniqueConstraint(
            "state_snapshot_id",
            "facet",
            "reason_code",
            name="uq_state_snapshot_reasons_code",
        ),
        sa.CheckConstraint("position >= 0", name="ck_state_snapshot_reasons_position"),
    )
    op.create_table(
        "state_snapshot_fit_criteria",
        sa.Column("state_snapshot_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fit_criterion_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("criterion_stable_key", sa.String(length=120), nullable=False),
        sa.Column("input_fact_key", sa.String(length=160), nullable=False),
        sa.Column(
            "source_strategy_evidence_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("expected_assertion", evidence_assertion, nullable=False),
        sa.Column("observed_assertion", evidence_assertion, nullable=True),
        sa.Column("criterion_result", fit_criterion_result, nullable=False),
        sa.ForeignKeyConstraint(
            ["state_snapshot_id", "workspace_id", "account_id", "strategy_version_id"],
            [
                "account_state_snapshots.state_snapshot_id",
                "account_state_snapshots.workspace_id",
                "account_state_snapshots.account_id",
                "account_state_snapshots.strategy_version_id",
            ],
            name="fk_state_snapshot_fit_criteria_snapshot_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["fit_criterion_id", "workspace_id", "strategy_version_id"],
            [
                "strategy_fit_criteria.fit_criterion_id",
                "strategy_fit_criteria.workspace_id",
                "strategy_fit_criteria.strategy_version_id",
            ],
            name="fk_state_snapshot_fit_criteria_criterion_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_strategy_evidence_id", "strategy_version_id"],
            ["evidence.id", "evidence.strategy_version_id"],
            name="fk_state_snapshot_fit_criteria_source_evidence",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "state_snapshot_id",
            "fit_criterion_id",
            name="uq_state_snapshot_fit_criteria_link",
        ),
    )
    op.create_table(
        "state_snapshot_evidence",
        sa.Column("state_snapshot_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("facet", account_state_facet, primary_key=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fit_criterion_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["state_snapshot_id", "account_id"],
            ["account_state_snapshots.state_snapshot_id", "account_state_snapshots.account_id"],
            name="fk_state_snapshot_evidence_snapshot_account",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id", "account_id"],
            ["evidence.id", "evidence.account_id"],
            name="fk_state_snapshot_evidence_evidence_account",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["state_snapshot_id", "fit_criterion_id"],
            [
                "state_snapshot_fit_criteria.state_snapshot_id",
                "state_snapshot_fit_criteria.fit_criterion_id",
            ],
            name="fk_state_snapshot_evidence_fit_criterion",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "(facet = 'FIT_CONTEXT' AND fit_criterion_id IS NOT NULL) "
            "OR (facet = 'RELATIONSHIP_STATE' AND fit_criterion_id IS NULL)",
            name="ck_state_snapshot_evidence_facet_shape",
        ),
    )
    op.create_index(
        "ix_state_snapshot_evidence_evidence_id",
        "state_snapshot_evidence",
        ["evidence_id"],
    )
    op.create_table(
        "state_snapshot_signal_evaluations",
        sa.Column("state_snapshot_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signal_definition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["state_snapshot_id", "workspace_id", "account_id", "strategy_version_id"],
            [
                "account_state_snapshots.state_snapshot_id",
                "account_state_snapshots.workspace_id",
                "account_state_snapshots.account_id",
                "account_state_snapshots.strategy_version_id",
            ],
            name="fk_state_snapshot_signal_evaluations_snapshot_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "evaluation_id",
                "workspace_id",
                "account_id",
                "signal_definition_id",
                "strategy_version_id",
            ],
            [
                "signal_evaluations.evaluation_id",
                "signal_evaluations.workspace_id",
                "signal_evaluations.account_id",
                "signal_evaluations.signal_definition_id",
                "signal_evaluations.strategy_version_id",
            ],
            name="fk_state_snapshot_signal_evaluations_evaluation_scope",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_state_snapshot_signal_evaluations_evaluation_id",
        "state_snapshot_signal_evaluations",
        ["evaluation_id"],
    )


def downgrade() -> None:
    """Remove M1B.2 while preserving the accepted M1B.1 foundation."""

    op.drop_index(
        "ix_state_snapshot_signal_evaluations_evaluation_id",
        table_name="state_snapshot_signal_evaluations",
    )
    op.drop_table("state_snapshot_signal_evaluations")
    op.drop_index(
        "ix_state_snapshot_evidence_evidence_id",
        table_name="state_snapshot_evidence",
    )
    op.drop_table("state_snapshot_evidence")
    op.drop_table("state_snapshot_fit_criteria")
    op.drop_table("state_snapshot_reasons")
    op.drop_index(
        "ix_account_state_snapshots_current",
        table_name="account_state_snapshots",
    )
    op.drop_table("account_state_snapshots")
    op.drop_table("strategy_fit_criteria")
    op.drop_constraint(
        "uq_evidence_id_strategy_version",
        "evidence",
        type_="unique",
    )

    account_state_reason_code.drop(op.get_bind(), checkfirst=True)
    fit_criterion_result.drop(op.get_bind(), checkfirst=True)
    account_state_facet.drop(op.get_bind(), checkfirst=True)
    account_evidence_sufficiency.drop(op.get_bind(), checkfirst=True)
    account_relationship_state.drop(op.get_bind(), checkfirst=True)
    account_timing_state.drop(op.get_bind(), checkfirst=True)
    account_fit_context.drop(op.get_bind(), checkfirst=True)
