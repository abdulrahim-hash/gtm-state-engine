"""Add governed Action and operational Outcome trace.

Revision ID: 20261003_0006
Revises: 20261003_0005
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261003_0006"
down_revision: str | None = "20261003_0005"
branch_labels: str | None = None
depends_on: str | None = None

action_type = postgresql.ENUM(
    "REQUEST_RESEARCH",
    "CREATE_SELLER_TASK",
    name="action_type",
    create_type=False,
)
action_review_resolution = postgresql.ENUM(
    "APPROVED",
    "REJECTED",
    name="action_review_resolution",
    create_type=False,
)
action_review_reason_code = postgresql.ENUM(
    "APPROVED_AS_PROPOSED",
    "REJECTED_INSUFFICIENT_CONTEXT",
    "REJECTED_ACTION_NOT_APPROPRIATE",
    name="action_review_reason_code",
    create_type=False,
)
action_actor_kind = postgresql.ENUM(
    "UNVERIFIED_DEMO_HUMAN",
    "SYNTHETIC_FIXTURE",
    name="action_actor_kind",
    create_type=False,
)
action_attempt_mode = postgresql.ENUM(
    "DRY_RUN",
    name="action_attempt_mode",
    create_type=False,
)
action_outcome_result = postgresql.ENUM(
    "SUCCEEDED",
    "FAILED",
    name="action_outcome_result",
    create_type=False,
)
action_outcome_reason_code = postgresql.ENUM(
    "CANONICAL_ACTION_VALIDATED",
    "CANONICAL_ACTION_INVALID",
    name="action_outcome_reason_code",
    create_type=False,
)


def upgrade() -> None:
    """Create schema-only M1D Action, Review, Attempt, and Outcome ledgers."""

    bind = op.get_bind()
    action_type.create(bind, checkfirst=True)
    action_review_resolution.create(bind, checkfirst=True)
    action_review_reason_code.create(bind, checkfirst=True)
    action_actor_kind.create(bind, checkfirst=True)
    action_attempt_mode.create(bind, checkfirst=True)
    action_outcome_result.create(bind, checkfirst=True)
    action_outcome_reason_code.create(bind, checkfirst=True)

    op.create_unique_constraint(
        "uq_policy_evaluations_action_scope",
        "policy_evaluations",
        [
            "policy_evaluation_id",
            "workspace_id",
            "account_id",
            "strategy_version_id",
        ],
    )

    op.create_table(
        "actions",
        sa.Column("action_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", action_type, nullable=False),
        sa.Column("action_schema_version", sa.String(length=32), nullable=False),
        sa.Column("derivation_key", sa.String(length=120), nullable=False),
        sa.Column("derivation_version", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("semantic_input_hash", sa.String(length=64), nullable=False),
        sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            [
                "policy_evaluation_id",
                "workspace_id",
                "account_id",
                "strategy_version_id",
            ],
            [
                "policy_evaluations.policy_evaluation_id",
                "policy_evaluations.workspace_id",
                "policy_evaluations.account_id",
                "policy_evaluations.strategy_version_id",
            ],
            name="fk_actions_policy_scope",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "policy_evaluation_id",
            "derivation_key",
            "derivation_version",
            name="uq_actions_policy_derivation",
        ),
        sa.UniqueConstraint(
            "semantic_input_hash",
            name="uq_actions_semantic_input_hash",
        ),
        sa.UniqueConstraint(
            "action_id",
            "workspace_id",
            "account_id",
            name="uq_actions_scope",
        ),
        sa.CheckConstraint(
            "semantic_input_hash ~ '^[a-f0-9]{64}$'",
            name="ck_actions_semantic_input_hash",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'",
            name="ck_actions_payload_object",
        ),
    )
    op.create_index(
        "ix_actions_account_history",
        "actions",
        ["workspace_id", "account_id", "proposed_at"],
    )
    op.create_index(
        "ix_actions_policy_evaluation",
        "actions",
        ["policy_evaluation_id"],
    )

    op.create_table(
        "action_reviews",
        sa.Column("review_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resolution", action_review_resolution, nullable=False),
        sa.Column("reason_code", action_review_reason_code, nullable=False),
        sa.Column("reviewer_kind", action_actor_kind, nullable=False),
        sa.Column("reviewer_ref", sa.String(length=120), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["actions.action_id"],
            name="fk_action_reviews_action",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "action_id",
            name="uq_action_reviews_one_terminal",
        ),
        sa.UniqueConstraint(
            "action_id",
            "idempotency_key_hash",
            name="uq_action_reviews_idempotency",
        ),
        sa.UniqueConstraint(
            "review_id",
            "action_id",
            name="uq_action_reviews_scope",
        ),
        sa.CheckConstraint(
            "idempotency_key_hash ~ '^[a-f0-9]{64}$'",
            name="ck_action_reviews_idempotency_hash",
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[a-f0-9]{64}$'",
            name="ck_action_reviews_request_hash",
        ),
    )
    op.create_table(
        "action_attempts",
        sa.Column("action_attempt_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("mode", action_attempt_mode, nullable=False),
        sa.Column("validator_key", sa.String(length=120), nullable=False),
        sa.Column("validator_version", sa.String(length=32), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("requested_by_kind", action_actor_kind, nullable=False),
        sa.Column("requested_by_ref", sa.String(length=120), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["actions.action_id"],
            name="fk_action_attempts_action",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["review_id", "action_id"],
            ["action_reviews.review_id", "action_reviews.action_id"],
            name="fk_action_attempts_review_scope",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "action_id",
            "mode",
            "validator_key",
            "validator_version",
            "input_hash",
            name="uq_action_attempts_semantic",
        ),
        sa.UniqueConstraint(
            "action_attempt_id",
            "action_id",
            name="uq_action_attempts_scope",
        ),
        sa.CheckConstraint(
            "input_hash ~ '^[a-f0-9]{64}$'",
            name="ck_action_attempts_input_hash",
        ),
    )
    op.create_index(
        "ix_action_attempts_action",
        "action_attempts",
        ["action_id", "attempted_at"],
    )
    op.create_table(
        "action_outcomes",
        sa.Column("outcome_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("result", action_outcome_result, nullable=False),
        sa.Column("reason_code", action_outcome_reason_code, nullable=False),
        sa.Column("outcome_schema_version", sa.String(length=32), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "external_side_effects",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["actions.action_id"],
            name="fk_action_outcomes_action",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["action_attempt_id", "action_id"],
            ["action_attempts.action_attempt_id", "action_attempts.action_id"],
            name="fk_action_outcomes_attempt_scope",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "action_attempt_id",
            name="uq_action_outcomes_one_per_attempt",
        ),
        sa.CheckConstraint(
            "result_hash ~ '^[a-f0-9]{64}$'",
            name="ck_action_outcomes_result_hash",
        ),
        sa.CheckConstraint(
            "external_side_effects = false",
            name="ck_action_outcomes_no_external_side_effects",
        ),
    )
    op.create_index(
        "ix_action_outcomes_action",
        "action_outcomes",
        ["action_id", "observed_at"],
    )


def downgrade() -> None:
    """Remove M1D while preserving the complete M1C ledgers."""

    op.drop_index("ix_action_outcomes_action", table_name="action_outcomes")
    op.drop_table("action_outcomes")
    op.drop_index("ix_action_attempts_action", table_name="action_attempts")
    op.drop_table("action_attempts")
    op.drop_table("action_reviews")
    op.drop_index("ix_actions_policy_evaluation", table_name="actions")
    op.drop_index("ix_actions_account_history", table_name="actions")
    op.drop_table("actions")
    op.drop_constraint(
        "uq_policy_evaluations_action_scope",
        "policy_evaluations",
        type_="unique",
    )

    action_outcome_reason_code.drop(op.get_bind(), checkfirst=True)
    action_outcome_result.drop(op.get_bind(), checkfirst=True)
    action_attempt_mode.drop(op.get_bind(), checkfirst=True)
    action_actor_kind.drop(op.get_bind(), checkfirst=True)
    action_review_reason_code.drop(op.get_bind(), checkfirst=True)
    action_review_resolution.drop(op.get_bind(), checkfirst=True)
    action_type.drop(op.get_bind(), checkfirst=True)
