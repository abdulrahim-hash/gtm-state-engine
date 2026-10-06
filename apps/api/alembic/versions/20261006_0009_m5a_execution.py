"""Add a separate, fail-closed developer-test execution ledger.

Revision ID: 20261006_0009
Revises: 20261005_0008
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261006_0009"
down_revision: str | None = "20261005_0008"
branch_labels: str | None = None
depends_on: str | None = None

UUID = postgresql.UUID(as_uuid=True)
HASH = sa.String(64)
TIME = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "execution_plans",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "action_id",
            UUID,
            sa.ForeignKey("actions.action_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("action_hash", HASH, nullable=False),
        sa.Column("policy_evaluation_id", UUID, nullable=False),
        sa.Column("policy_hash", HASH, nullable=False),
        sa.Column("decision_evaluation_id", UUID, nullable=False),
        sa.Column("state_snapshot_id", UUID, nullable=False),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("adapter_key", sa.String(80), nullable=False),
        sa.Column("adapter_version", sa.String(32), nullable=False),
        sa.Column("api_version", sa.String(16), nullable=False),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("portal_scope_hash", HASH, nullable=False),
        sa.Column("provider_company_id", sa.String(30), nullable=False),
        sa.Column("provider_owner_id", sa.String(30), nullable=False),
        sa.Column("association_type_id", sa.Integer(), nullable=False),
        sa.Column("task_fields", postgresql.JSONB(), nullable=False),
        sa.Column("marker", sa.String(40), nullable=False),
        sa.Column("schema_version", sa.String(16), nullable=False),
        sa.Column("plan_hash", HASH, nullable=False),
        sa.Column("created_at", TIME, nullable=False),
        sa.UniqueConstraint("plan_hash", name="uq_execution_plans_hash"),
        sa.UniqueConstraint("marker", name="uq_execution_plans_marker"),
        sa.UniqueConstraint("id", "action_id", name="uq_execution_plans_action_scope"),
        sa.ForeignKeyConstraint(
            ["action_id", "workspace_id", "account_id"],
            ["actions.action_id", "actions.workspace_id", "actions.account_id"],
            name="fk_execution_plans_action_scope",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("plan_hash ~ '^[a-f0-9]{64}$'", name="ck_execution_plans_hash"),
        sa.CheckConstraint(
            "portal_scope_hash ~ '^[a-f0-9]{64}$'", name="ck_execution_plans_portal_hash"
        ),
        sa.CheckConstraint("operation = 'CREATE_SELLER_TASK'", name="ck_execution_plans_operation"),
        sa.CheckConstraint(
            "jsonb_typeof(task_fields) = 'object'", name="ck_execution_plans_task_object"
        ),
    )
    op.create_table(
        "execution_authorizations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("execution_plan_id", UUID, nullable=False),
        sa.Column("action_id", UUID, nullable=False),
        sa.Column("action_hash", HASH, nullable=False),
        sa.Column("plan_hash", HASH, nullable=False),
        sa.Column("portal_scope_hash", HASH, nullable=False),
        sa.Column("provider_company_id", sa.String(30), nullable=False),
        sa.Column("provider_owner_id", sa.String(30), nullable=False),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("assurance_type", sa.String(40), nullable=False),
        sa.Column("operator_ref", sa.String(120), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("authorized_at", TIME, nullable=False),
        sa.Column("expires_at", TIME, nullable=False),
        sa.UniqueConstraint("execution_plan_id", name="uq_execution_authorizations_plan"),
        sa.UniqueConstraint(
            "id", "execution_plan_id", name="uq_execution_authorizations_plan_scope"
        ),
        sa.ForeignKeyConstraint(
            ["execution_plan_id", "action_id"],
            ["execution_plans.id", "execution_plans.action_id"],
            name="fk_execution_authorizations_plan_action",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "assurance_type = 'LOCAL_OPERATOR_ATTESTATION'",
            name="ck_execution_authorizations_assurance",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','REVOKED')", name="ck_execution_authorizations_status"
        ),
        sa.CheckConstraint("expires_at > authorized_at", name="ck_execution_authorizations_expiry"),
    )
    op.create_table(
        "execution_attempts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("execution_plan_id", UUID, nullable=False),
        sa.Column("action_id", UUID, nullable=False),
        sa.Column("authorization_id", UUID, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("dispatch_id", UUID, unique=True, nullable=True),
        sa.Column("physical_post_count", sa.Integer(), nullable=False),
        sa.Column("lease_until", TIME, nullable=True),
        sa.Column("dispatched_at", TIME, nullable=True),
        sa.Column("failure_code", sa.String(64), nullable=True),
        sa.Column("safe_correlation", sa.String(120), nullable=True),
        sa.Column("delivery_duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("created_at", TIME, nullable=False),
        sa.Column("updated_at", TIME, nullable=False),
        sa.UniqueConstraint("execution_plan_id", name="uq_execution_attempts_plan"),
        sa.UniqueConstraint("action_id", name="uq_execution_attempts_action_one_delivery"),
        sa.UniqueConstraint("authorization_id", name="uq_execution_attempts_authorization"),
        sa.ForeignKeyConstraint(
            ["execution_plan_id", "action_id"],
            ["execution_plans.id", "execution_plans.action_id"],
            name="fk_execution_attempts_plan_action",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["authorization_id", "execution_plan_id"],
            ["execution_authorizations.id", "execution_authorizations.execution_plan_id"],
            name="fk_execution_attempts_authorization_plan",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "physical_post_count BETWEEN 0 AND 1", name="ck_execution_attempts_one_post"
        ),
        sa.CheckConstraint(
            "delivery_duration_ms IS NULL OR delivery_duration_ms >= 0",
            name="ck_execution_attempts_duration",
        ),
        sa.CheckConstraint(
            """status IN (
                'NOT_ATTEMPTED','IN_FLIGHT','PROVIDER_ACCEPTED','CONFIRMED',
                'REJECTED_NO_WRITE','UNKNOWN_DELIVERY','MISMATCH'
            )""",
            name="ck_execution_attempts_status",
        ),
        sa.CheckConstraint(
            """(status = 'NOT_ATTEMPTED' AND physical_post_count = 0) OR
               (status <> 'NOT_ATTEMPTED' AND physical_post_count = 1)""",
            name="ck_execution_attempts_dispatch_count",
        ),
    )
    op.create_table(
        "execution_attempt_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "execution_attempt_id",
            UUID,
            sa.ForeignKey("execution_attempts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("previous_state", sa.String(24), nullable=True),
        sa.Column("new_state", sa.String(24), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("safe_correlation", sa.String(120), nullable=True),
        sa.Column("occurred_at", TIME, nullable=False),
        sa.UniqueConstraint(
            "execution_attempt_id", "sequence", name="uq_execution_attempt_events_sequence"
        ),
        sa.CheckConstraint("sequence >= 0", name="ck_execution_attempt_events_sequence"),
    )
    op.create_table(
        "provider_receipts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "execution_plan_id",
            UUID,
            sa.ForeignKey("execution_plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "execution_attempt_id",
            UUID,
            sa.ForeignKey("execution_attempts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("provider_type", sa.String(20), nullable=False),
        sa.Column("portal_scope_hash", HASH, nullable=False),
        sa.Column("provider_object_type", sa.String(20), nullable=False),
        sa.Column("provider_object_id", sa.String(30), nullable=False),
        sa.Column("request_correlation", sa.String(120), nullable=True),
        sa.Column("http_result_class", sa.String(24), nullable=False),
        sa.Column("provider_timestamp", TIME, nullable=True),
        sa.Column("adapter_version", sa.String(32), nullable=False),
        sa.Column("api_version", sa.String(16), nullable=False),
        sa.Column("request_hash", HASH, nullable=False),
        sa.Column("response_hash", HASH, nullable=False),
        sa.Column("recorded_at", TIME, nullable=False),
        sa.UniqueConstraint("execution_attempt_id", name="uq_provider_receipts_attempt"),
        sa.UniqueConstraint(
            "portal_scope_hash", "provider_object_id", name="uq_provider_receipts_task"
        ),
        sa.CheckConstraint(
            "provider_type = 'HUBSPOT' AND provider_object_type = 'TASK'",
            name="ck_provider_receipts_kind",
        ),
    )
    op.create_table(
        "execution_reconciliations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "execution_attempt_id",
            UUID,
            sa.ForeignKey("execution_attempts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "provider_receipt_id",
            UUID,
            sa.ForeignKey("provider_receipts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("provider_task_id", sa.String(30), nullable=True),
        sa.Column("read_count", sa.Integer(), nullable=False),
        sa.Column("observed_hash", HASH, nullable=True),
        sa.Column("reconciled_at", TIME, nullable=False),
        sa.CheckConstraint(
            "result IN ('CONFIRMED','NOT_FOUND','MISMATCH','UNKNOWN')",
            name="ck_execution_reconciliations_result",
        ),
        sa.CheckConstraint(
            "read_count BETWEEN 0 AND 20", name="ck_execution_reconciliations_read_count"
        ),
    )
    op.create_table(
        "operational_outcomes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "execution_plan_id",
            UUID,
            sa.ForeignKey("execution_plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "execution_attempt_id",
            UUID,
            sa.ForeignKey("execution_attempts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "execution_reconciliation_id",
            UUID,
            sa.ForeignKey("execution_reconciliations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("observed_at", TIME, nullable=False),
        sa.UniqueConstraint("execution_plan_id", name="uq_operational_outcomes_plan"),
        sa.UniqueConstraint("execution_attempt_id", name="uq_operational_outcomes_attempt"),
        sa.CheckConstraint(
            "reason_code = 'CRM_TASK_CONFIRMED_CREATED'", name="ck_operational_outcomes_reason"
        ),
    )
    op.execute("""
        CREATE FUNCTION m5a_reject_history_change() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'M5A provenance is append-only';
        END;
        $$ LANGUAGE plpgsql
    """)
    for table in (
        "execution_plans",
        "execution_attempt_events",
        "provider_receipts",
        "execution_reconciliations",
        "operational_outcomes",
    ):
        op.execute(
            sa.text(
                f"CREATE TRIGGER m5a_immutable BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION m5a_reject_history_change()"
            )
        )
    op.execute("""
        CREATE FUNCTION m5a_guard_attempt_update() RETURNS trigger AS $$
        BEGIN
            IF NEW.execution_plan_id <> OLD.execution_plan_id
               OR NEW.action_id <> OLD.action_id
               OR NEW.authorization_id <> OLD.authorization_id
               OR NEW.physical_post_count < OLD.physical_post_count
               OR (OLD.physical_post_count = 1 AND NEW.dispatch_id IS DISTINCT FROM OLD.dispatch_id)
            THEN
                RAISE EXCEPTION 'M5A attempt binding or POST reservation cannot change';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER m5a_attempt_guard BEFORE UPDATE ON execution_attempts
        FOR EACH ROW EXECUTE FUNCTION m5a_guard_attempt_update()
    """)
    op.execute("""
        CREATE FUNCTION m5a_guard_authorization_update() RETURNS trigger AS $$
        BEGIN
            IF (to_jsonb(NEW) - 'status') <> (to_jsonb(OLD) - 'status')
               OR NOT (OLD.status = 'ACTIVE' AND NEW.status = 'REVOKED')
            THEN
                RAISE EXCEPTION 'M5A authorization binding is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER m5a_authorization_guard
        BEFORE UPDATE ON execution_authorizations
        FOR EACH ROW EXECUTE FUNCTION m5a_guard_authorization_update()
    """)
    op.execute("""
        CREATE TRIGGER m5a_authorization_no_delete
        BEFORE DELETE ON execution_authorizations
        FOR EACH ROW EXECUTE FUNCTION m5a_reject_history_change()
    """)
    op.execute("""
        CREATE FUNCTION m5a_guard_operational_outcome() RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM execution_reconciliations r
                JOIN execution_attempts a ON a.id = r.execution_attempt_id
                WHERE r.id = NEW.execution_reconciliation_id
                  AND r.result = 'CONFIRMED'
                  AND r.execution_attempt_id = NEW.execution_attempt_id
                  AND a.execution_plan_id = NEW.execution_plan_id
                  AND a.status = 'CONFIRMED'
            ) THEN
                RAISE EXCEPTION 'M5A operational outcome requires confirmed reconciliation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER m5a_operational_outcome_guard
        BEFORE INSERT ON operational_outcomes
        FOR EACH ROW EXECUTE FUNCTION m5a_guard_operational_outcome()
    """)


def downgrade() -> None:
    bind = op.get_bind()
    for table in (
        "execution_plans",
        "execution_authorizations",
        "execution_attempts",
        "execution_attempt_events",
        "provider_receipts",
        "execution_reconciliations",
        "operational_outcomes",
    ):
        if bind.scalar(sa.text(f"SELECT count(*) FROM {table}")):
            raise RuntimeError("M5A execution history exists; downgrade would destroy provenance")
    for table in (
        "operational_outcomes",
        "execution_reconciliations",
        "provider_receipts",
        "execution_attempt_events",
        "execution_attempts",
        "execution_authorizations",
        "execution_plans",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION IF EXISTS m5a_guard_operational_outcome()")
    op.execute("DROP FUNCTION IF EXISTS m5a_guard_authorization_update()")
    op.execute("DROP FUNCTION m5a_guard_attempt_update()")
    op.execute("DROP FUNCTION m5a_reject_history_change()")
