"""Add deterministic evidence-to-signal evaluation and canonical events.

Revision ID: 20260930_0003
Revises: 20260929_0002
Create Date: 2026-09-30
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260930_0003"
down_revision: str | None = "20260929_0002"
branch_labels: str | None = None
depends_on: str | None = None

evidence_assertion = postgresql.ENUM(
    "PRESENT", "ABSENT", "INCONCLUSIVE", name="evidence_assertion", create_type=False
)
signal_category = postgresql.ENUM(
    "LEADERSHIP",
    "HIRING",
    "FUNDING",
    "EXPANSION",
    "TECHNOLOGY",
    "ENGAGEMENT",
    name="signal_category",
    create_type=False,
)
signal_definition_status = postgresql.ENUM(
    "ENABLED", "DISABLED", name="signal_definition_status", create_type=False
)
signal_evaluation_result = postgresql.ENUM(
    "DETECTED",
    "NO_MATCH",
    "INCONCLUSIVE",
    "STALE",
    name="signal_evaluation_result",
    create_type=False,
)
signal_reason_code = postgresql.ENUM(
    "QUALIFYING_EVENT_WITHIN_WINDOW",
    "QUALIFYING_EVENT_OUTSIDE_WINDOW",
    "SUFFICIENT_EVIDENCE_NO_EVENT",
    "REQUIRED_EVIDENCE_MISSING",
    "EVIDENCE_AMBIGUOUS",
    "EVIDENCE_CONTRADICTORY",
    name="signal_reason_code",
    create_type=False,
)


def upgrade() -> None:
    """Create M1B.1's deterministic evaluation ledger and canonical signal events."""

    evidence_assertion.create(op.get_bind(), checkfirst=True)
    signal_category.create(op.get_bind(), checkfirst=True)
    signal_definition_status.create(op.get_bind(), checkfirst=True)
    signal_evaluation_result.create(op.get_bind(), checkfirst=True)
    signal_reason_code.create(op.get_bind(), checkfirst=True)

    op.add_column("evidence", sa.Column("fact_key", sa.String(length=160), nullable=True))
    op.add_column("evidence", sa.Column("fact_assertion", evidence_assertion, nullable=True))
    op.create_check_constraint(
        "ck_evidence_fact_shape",
        "evidence",
        "(fact_key IS NULL AND fact_assertion IS NULL) "
        "OR (fact_key IS NOT NULL AND fact_assertion IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_evidence_fact_key",
        "evidence",
        "fact_key IS NULL OR fact_key ~ '^[a-z][a-z0-9_.]*$'",
    )
    op.create_unique_constraint(
        "uq_strategy_versions_id_workspace", "strategy_versions", ["id", "workspace_id"]
    )
    op.create_unique_constraint("uq_accounts_id_workspace", "accounts", ["id", "workspace_id"])
    op.create_unique_constraint("uq_evidence_id_account", "evidence", ["id", "account_id"])

    op.create_table(
        "signal_definitions",
        sa.Column("signal_definition_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stable_key", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", signal_category, nullable=False),
        sa.Column("input_fact_key", sa.String(length=160), nullable=False),
        sa.Column("evaluator_key", sa.String(length=120), nullable=False),
        sa.Column("freshness_window_days", sa.Integer(), nullable=False),
        sa.Column("rule_version", sa.String(length=32), nullable=False),
        sa.Column("status", signal_definition_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_version_id", "workspace_id"],
            ["strategy_versions.id", "strategy_versions.workspace_id"],
            name="fk_signal_definitions_strategy_workspace",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "strategy_version_id",
            "stable_key",
            "rule_version",
            name="uq_signal_definitions_version",
        ),
        sa.UniqueConstraint(
            "signal_definition_id",
            "workspace_id",
            "strategy_version_id",
            name="uq_signal_definitions_scope",
        ),
        sa.CheckConstraint("freshness_window_days > 0", name="ck_signal_definition_freshness"),
        sa.CheckConstraint(
            "stable_key ~ '^[a-z][a-z0-9_]*$'",
            name="ck_signal_definition_stable_key",
        ),
        sa.CheckConstraint(
            "input_fact_key ~ '^[a-z][a-z0-9_.]*$'",
            name="ck_signal_definition_input_fact_key",
        ),
        sa.CheckConstraint(
            "evaluator_key ~ '^[a-z][a-z0-9_]*$'",
            name="ck_signal_definition_evaluator_key",
        ),
    )
    op.create_index(
        "uq_signal_definitions_one_enabled",
        "signal_definitions",
        ["strategy_version_id", "stable_key"],
        unique=True,
        postgresql_where=sa.text("status = 'ENABLED'"),
    )
    op.create_index(
        "ix_signal_definitions_workspace_strategy",
        "signal_definitions",
        ["workspace_id", "strategy_version_id"],
    )

    op.create_table(
        "signal_evaluations",
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signal_definition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evaluation_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("result", signal_evaluation_result, nullable=False),
        sa.Column("reason_code", signal_reason_code, nullable=False),
        sa.Column("rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id", "workspace_id"],
            ["accounts.id", "accounts.workspace_id"],
            name="fk_signal_evaluations_account_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["signal_definition_id", "workspace_id", "strategy_version_id"],
            [
                "signal_definitions.signal_definition_id",
                "signal_definitions.workspace_id",
                "signal_definitions.strategy_version_id",
            ],
            name="fk_signal_evaluations_definition_scope",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "account_id",
            "signal_definition_id",
            "strategy_version_id",
            "evaluation_as_of",
            "input_hash",
            name="uq_signal_evaluations_input",
        ),
        sa.UniqueConstraint("evaluation_id", "account_id", name="uq_signal_evaluations_id_account"),
        sa.UniqueConstraint(
            "evaluation_id",
            "workspace_id",
            "account_id",
            "signal_definition_id",
            "strategy_version_id",
            name="uq_signal_evaluations_scope",
        ),
        sa.CheckConstraint("input_hash ~ '^[a-f0-9]{64}$'", name="ck_signal_evaluation_hash"),
    )
    op.create_index(
        "ix_signal_evaluations_account_as_of",
        "signal_evaluations",
        ["account_id", "evaluation_as_of"],
    )
    op.create_index("ix_signal_evaluations_signal_id", "signal_evaluations", ["signal_id"])

    op.create_table(
        "evaluation_evidence",
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["evaluation_id", "account_id"],
            ["signal_evaluations.evaluation_id", "signal_evaluations.account_id"],
            name="fk_evaluation_evidence_evaluation_account",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id", "account_id"],
            ["evidence.id", "evidence.account_id"],
            name="fk_evaluation_evidence_evidence_account",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_evaluation_evidence_evidence_id", "evaluation_evidence", ["evidence_id"])

    op.create_table(
        "signals",
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signal_definition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("origin_evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            [
                "origin_evaluation_id",
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
            name="fk_signals_origin_evaluation_scope",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("event_fingerprint", name="uq_signals_event_fingerprint"),
        sa.UniqueConstraint("origin_evaluation_id", name="uq_signals_origin_evaluation"),
        sa.UniqueConstraint(
            "signal_id",
            "workspace_id",
            "account_id",
            "signal_definition_id",
            "strategy_version_id",
            name="uq_signals_scope",
        ),
        sa.CheckConstraint(
            "event_fingerprint ~ '^[a-f0-9]{64}$'",
            name="ck_signals_event_fingerprint",
        ),
    )
    op.create_index("ix_signals_account_observed", "signals", ["account_id", "observed_at"])
    op.create_foreign_key(
        "fk_signal_evaluations_signal_scope",
        "signal_evaluations",
        "signals",
        [
            "signal_id",
            "workspace_id",
            "account_id",
            "signal_definition_id",
            "strategy_version_id",
        ],
        [
            "signal_id",
            "workspace_id",
            "account_id",
            "signal_definition_id",
            "strategy_version_id",
        ],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Remove M1B.1 while preserving the accepted M1A foundation."""

    op.drop_constraint(
        "fk_signal_evaluations_signal_scope", "signal_evaluations", type_="foreignkey"
    )
    op.drop_index("ix_signals_account_observed", table_name="signals")
    op.drop_table("signals")
    op.drop_index("ix_evaluation_evidence_evidence_id", table_name="evaluation_evidence")
    op.drop_table("evaluation_evidence")
    op.drop_index("ix_signal_evaluations_signal_id", table_name="signal_evaluations")
    op.drop_index("ix_signal_evaluations_account_as_of", table_name="signal_evaluations")
    op.drop_table("signal_evaluations")
    op.drop_index("ix_signal_definitions_workspace_strategy", table_name="signal_definitions")
    op.drop_index("uq_signal_definitions_one_enabled", table_name="signal_definitions")
    op.drop_table("signal_definitions")
    op.drop_constraint("uq_evidence_id_account", "evidence", type_="unique")
    op.drop_constraint("uq_accounts_id_workspace", "accounts", type_="unique")
    op.drop_constraint("uq_strategy_versions_id_workspace", "strategy_versions", type_="unique")
    op.drop_constraint("ck_evidence_fact_key", "evidence", type_="check")
    op.drop_constraint("ck_evidence_fact_shape", "evidence", type_="check")
    op.drop_column("evidence", "fact_assertion")
    op.drop_column("evidence", "fact_key")

    signal_reason_code.drop(op.get_bind(), checkfirst=True)
    signal_evaluation_result.drop(op.get_bind(), checkfirst=True)
    signal_definition_status.drop(op.get_bind(), checkfirst=True)
    signal_category.drop(op.get_bind(), checkfirst=True)
    evidence_assertion.drop(op.get_bind(), checkfirst=True)
