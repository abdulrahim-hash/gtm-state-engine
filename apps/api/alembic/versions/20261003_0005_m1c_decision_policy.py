"""Add deterministic Decision and Policy evaluations.

Revision ID: 20261003_0005
Revises: 20261002_0004
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261003_0005"
down_revision: str | None = "20261002_0004"
branch_labels: str | None = None
depends_on: str | None = None

evaluation_definition_status = postgresql.ENUM(
    "ENABLED", "DISABLED", name="evaluation_definition_status", create_type=False
)
decision_result = postgresql.ENUM(
    "ENGAGE", "HOLD", "NO_ACTION", "ABSTAIN", name="decision_result", create_type=False
)
decision_reason_code = postgresql.ENUM(
    "FIT_MATCH_SUPPORTS_ENGAGEMENT",
    "ACTIVE_TIMING_SUPPORTS_ENGAGEMENT",
    "FIT_MISMATCH_NO_PROSPECTING_BASIS",
    "FIT_MATCH_BUT_NO_CURRENT_TIMING",
    "FIT_MATCH_BUT_TIMING_STALE",
    "FIT_NOT_DETERMINATE",
    "TIMING_NOT_DETERMINATE",
    "STATE_EVIDENCE_INSUFFICIENT",
    "STATE_EVIDENCE_CONTRADICTORY",
    name="decision_reason_code",
    create_type=False,
)
policy_target = postgresql.ENUM("PROSPECTING_ACTIVATION", name="policy_target", create_type=False)
policy_result = postgresql.ENUM(
    "ALLOW", "REQUIRE_REVIEW", "BLOCK", name="policy_result", create_type=False
)
policy_reason_code = postgresql.ENUM(
    "DECISION_DOES_NOT_SUPPORT_ACTIVATION",
    "FIT_STATE_BLOCKS_ACTIVATION",
    "TIMING_STATE_BLOCKS_ACTIVATION",
    "EVIDENCE_INSUFFICIENT_BLOCKS_ACTIVATION",
    "EVIDENCE_CONTRADICTORY_BLOCKS_ACTIVATION",
    "DECISION_STATE_MISMATCH",
    "EXISTING_RELATIONSHIP_REQUIRES_CONTROLLED_HANDLING",
    "RELATIONSHIP_UNKNOWN_REQUIRES_REVIEW",
    "RELATIONSHIP_INCONCLUSIVE_REQUIRES_REVIEW",
    "PARTIAL_EVIDENCE_REQUIRES_REVIEW",
    "EXPLICIT_NO_EXISTING_RELATIONSHIP",
    "ALL_POLICY_CONSTRAINTS_SATISFIED",
    name="policy_reason_code",
    create_type=False,
)


def upgrade() -> None:
    """Create the schema-only M1C Decision and Policy ledgers."""

    bind = op.get_bind()
    evaluation_definition_status.create(bind, checkfirst=True)
    decision_result.create(bind, checkfirst=True)
    decision_reason_code.create(bind, checkfirst=True)
    policy_target.create(bind, checkfirst=True)
    policy_result.create(bind, checkfirst=True)
    policy_reason_code.create(bind, checkfirst=True)

    op.create_table(
        "decision_definitions",
        sa.Column("decision_definition_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stable_key", sa.String(length=120), nullable=False),
        sa.Column("definition_version", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evaluator_key", sa.String(length=120), nullable=False),
        sa.Column("evaluator_version", sa.String(length=32), nullable=False),
        sa.Column("status", evaluation_definition_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_version_id", "workspace_id"],
            ["strategy_versions.id", "strategy_versions.workspace_id"],
            name="fk_decision_definitions_strategy_workspace",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "strategy_version_id",
            "stable_key",
            "definition_version",
            name="uq_decision_definitions_version",
        ),
        sa.UniqueConstraint(
            "decision_definition_id",
            "workspace_id",
            "strategy_version_id",
            "definition_version",
            name="uq_decision_definitions_scope",
        ),
        sa.CheckConstraint(
            "stable_key ~ '^[a-z][a-z0-9_]*$'",
            name="ck_decision_definitions_stable_key",
        ),
        sa.CheckConstraint(
            "evaluator_key ~ '^[a-z][a-z0-9_]*$'",
            name="ck_decision_definitions_evaluator_key",
        ),
    )
    op.create_index(
        "uq_decision_definitions_one_enabled",
        "decision_definitions",
        ["workspace_id", "strategy_version_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ENABLED'"),
    )

    op.create_table(
        "decision_evaluations",
        sa.Column("decision_evaluation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_definition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("definition_version", sa.String(length=32), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("result", decision_result, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["state_snapshot_id", "workspace_id", "account_id", "strategy_version_id"],
            [
                "account_state_snapshots.state_snapshot_id",
                "account_state_snapshots.workspace_id",
                "account_state_snapshots.account_id",
                "account_state_snapshots.strategy_version_id",
            ],
            name="fk_decision_evaluations_snapshot_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "decision_definition_id",
                "workspace_id",
                "strategy_version_id",
                "definition_version",
            ],
            [
                "decision_definitions.decision_definition_id",
                "decision_definitions.workspace_id",
                "decision_definitions.strategy_version_id",
                "decision_definitions.definition_version",
            ],
            name="fk_decision_evaluations_definition_scope",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "state_snapshot_id",
            "decision_definition_id",
            name="uq_decision_evaluations_snapshot_definition",
        ),
        sa.UniqueConstraint(
            "decision_evaluation_id",
            "workspace_id",
            "account_id",
            "strategy_version_id",
            "state_snapshot_id",
            name="uq_decision_evaluations_scope",
        ),
        sa.CheckConstraint(
            "input_hash ~ '^[a-f0-9]{64}$'",
            name="ck_decision_evaluations_input_hash",
        ),
    )
    op.create_index(
        "ix_decision_evaluations_account_history",
        "decision_evaluations",
        ["workspace_id", "account_id", "strategy_version_id", "evaluated_at"],
    )

    op.create_table(
        "decision_evaluation_reasons",
        sa.Column("decision_evaluation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("reason_code", decision_reason_code, nullable=False),
        sa.ForeignKeyConstraint(
            ["decision_evaluation_id"],
            ["decision_evaluations.decision_evaluation_id"],
            name="fk_decision_evaluation_reasons_evaluation",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "decision_evaluation_id",
            "reason_code",
            name="uq_decision_evaluation_reasons_code",
        ),
        sa.CheckConstraint("position >= 0", name="ck_decision_evaluation_reasons_position"),
    )

    op.create_table(
        "policy_definitions",
        sa.Column("policy_definition_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stable_key", sa.String(length=120), nullable=False),
        sa.Column("definition_version", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("target", policy_target, nullable=False),
        sa.Column("evaluator_key", sa.String(length=120), nullable=False),
        sa.Column("evaluator_version", sa.String(length=32), nullable=False),
        sa.Column("status", evaluation_definition_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_version_id", "workspace_id"],
            ["strategy_versions.id", "strategy_versions.workspace_id"],
            name="fk_policy_definitions_strategy_workspace",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "strategy_version_id",
            "stable_key",
            "definition_version",
            name="uq_policy_definitions_version",
        ),
        sa.UniqueConstraint(
            "policy_definition_id",
            "workspace_id",
            "strategy_version_id",
            "definition_version",
            name="uq_policy_definitions_scope",
        ),
        sa.CheckConstraint(
            "stable_key ~ '^[a-z][a-z0-9_]*$'",
            name="ck_policy_definitions_stable_key",
        ),
        sa.CheckConstraint(
            "evaluator_key ~ '^[a-z][a-z0-9_]*$'",
            name="ck_policy_definitions_evaluator_key",
        ),
    )
    op.create_index(
        "uq_policy_definitions_one_enabled",
        "policy_definitions",
        ["workspace_id", "strategy_version_id", "target"],
        unique=True,
        postgresql_where=sa.text("status = 'ENABLED'"),
    )

    op.create_table(
        "policy_evaluations",
        sa.Column("policy_evaluation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_definition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("definition_version", sa.String(length=32), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("result", policy_result, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["state_snapshot_id", "workspace_id", "account_id", "strategy_version_id"],
            [
                "account_state_snapshots.state_snapshot_id",
                "account_state_snapshots.workspace_id",
                "account_state_snapshots.account_id",
                "account_state_snapshots.strategy_version_id",
            ],
            name="fk_policy_evaluations_snapshot_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "decision_evaluation_id",
                "workspace_id",
                "account_id",
                "strategy_version_id",
                "state_snapshot_id",
            ],
            [
                "decision_evaluations.decision_evaluation_id",
                "decision_evaluations.workspace_id",
                "decision_evaluations.account_id",
                "decision_evaluations.strategy_version_id",
                "decision_evaluations.state_snapshot_id",
            ],
            name="fk_policy_evaluations_decision_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "policy_definition_id",
                "workspace_id",
                "strategy_version_id",
                "definition_version",
            ],
            [
                "policy_definitions.policy_definition_id",
                "policy_definitions.workspace_id",
                "policy_definitions.strategy_version_id",
                "policy_definitions.definition_version",
            ],
            name="fk_policy_evaluations_definition_scope",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "decision_evaluation_id",
            "policy_definition_id",
            name="uq_policy_evaluations_decision_definition",
        ),
        sa.CheckConstraint(
            "input_hash ~ '^[a-f0-9]{64}$'",
            name="ck_policy_evaluations_input_hash",
        ),
    )
    op.create_index(
        "ix_policy_evaluations_decision",
        "policy_evaluations",
        ["decision_evaluation_id"],
    )

    op.create_table(
        "policy_evaluation_reasons",
        sa.Column("policy_evaluation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("reason_code", policy_reason_code, nullable=False),
        sa.ForeignKeyConstraint(
            ["policy_evaluation_id"],
            ["policy_evaluations.policy_evaluation_id"],
            name="fk_policy_evaluation_reasons_evaluation",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "policy_evaluation_id",
            "reason_code",
            name="uq_policy_evaluation_reasons_code",
        ),
        sa.CheckConstraint("position >= 0", name="ck_policy_evaluation_reasons_position"),
    )


def downgrade() -> None:
    """Remove M1C while preserving the complete M1B.2 state ledger."""

    op.drop_table("policy_evaluation_reasons")
    op.drop_index("ix_policy_evaluations_decision", table_name="policy_evaluations")
    op.drop_table("policy_evaluations")
    op.drop_index("uq_policy_definitions_one_enabled", table_name="policy_definitions")
    op.drop_table("policy_definitions")
    op.drop_table("decision_evaluation_reasons")
    op.drop_index("ix_decision_evaluations_account_history", table_name="decision_evaluations")
    op.drop_table("decision_evaluations")
    op.drop_index("uq_decision_definitions_one_enabled", table_name="decision_definitions")
    op.drop_table("decision_definitions")

    policy_reason_code.drop(op.get_bind(), checkfirst=True)
    policy_result.drop(op.get_bind(), checkfirst=True)
    policy_target.drop(op.get_bind(), checkfirst=True)
    decision_reason_code.drop(op.get_bind(), checkfirst=True)
    decision_result.drop(op.get_bind(), checkfirst=True)
    evaluation_definition_status.drop(op.get_bind(), checkfirst=True)
