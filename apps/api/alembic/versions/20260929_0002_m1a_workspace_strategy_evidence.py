"""Add workspace-scoped M1A strategy, account, and evidence foundations.

Revision ID: 20260929_0002
Revises: 20260929_0001
Create Date: 2026-09-29
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260929_0002"
down_revision: str | None = "20260929_0001"
branch_labels: str | None = None
depends_on: str | None = None

strategy_status = postgresql.ENUM(
    "DRAFT", "ACTIVE", "RETIRED", name="strategy_status", create_type=False
)
evidence_classification = postgresql.ENUM(
    "FACT", "INFERENCE", "HYPOTHESIS", name="evidence_classification", create_type=False
)
evidence_freshness = postgresql.ENUM(
    "CURRENT", "STALE", "UNKNOWN", name="evidence_freshness", create_type=False
)
strategy_topic = postgresql.ENUM(
    "MARKET",
    "SEGMENTATION",
    "ICP",
    "BUYER_HYPOTHESES",
    "PROBLEM_HYPOTHESIS",
    "VALUE_PROPOSITION_HYPOTHESIS",
    "OFFER_HYPOTHESIS",
    "PRICING_HYPOTHESIS",
    "MESSAGING_FRAMEWORK",
    "CHANNELS",
    "GTM_MOTION",
    "EXPERIMENT_ASSUMPTIONS",
    name="strategy_topic",
    create_type=False,
)


def upgrade() -> None:
    """Create only M1A's workspace, strategy, account, and evidence schema."""

    strategy_status.create(op.get_bind(), checkfirst=True)
    evidence_classification.create(op.get_bind(), checkfirst=True)
    evidence_freshness.create(op.get_bind(), checkfirst=True)
    strategy_topic.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "workspaces",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(length=80), nullable=False, unique=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("demo_mode", sa.Boolean(), nullable=False),
        sa.Column("demo_as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "strategy_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("semantic_version", sa.String(length=32), nullable=False),
        sa.Column("status", strategy_status, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("synthetic_disclaimer", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "workspace_id", "semantic_version", name="uq_strategy_versions_workspace_version"
        ),
    )
    op.create_index(
        "uq_strategy_versions_one_active_per_workspace",
        "strategy_versions",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("canonical_name", sa.String(length=200), nullable=False),
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("segment", sa.String(length=160), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_accounts_workspace_slug"),
        sa.UniqueConstraint("workspace_id", "domain", name="uq_accounts_workspace_domain"),
    )
    op.create_table(
        "evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "strategy_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("strategy_versions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("strategy_topic", strategy_topic, nullable=True),
        sa.Column("classification", evidence_classification, nullable=False),
        sa.Column("source_provider", sa.String(length=120), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("normalized_fact", sa.Text(), nullable=False),
        sa.Column("raw_payload_hash", sa.String(length=64), nullable=True),
        sa.Column("freshness", evidence_freshness, nullable=False),
        sa.Column("confidence", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.CheckConstraint(
            "(strategy_version_id IS NOT NULL AND account_id IS NULL) "
            "OR (strategy_version_id IS NULL AND account_id IS NOT NULL)",
            name="ck_evidence_exactly_one_target",
        ),
        sa.CheckConstraint(
            "(strategy_version_id IS NOT NULL AND strategy_topic IS NOT NULL) "
            "OR (strategy_version_id IS NULL AND strategy_topic IS NULL)",
            name="ck_evidence_strategy_topic_matches_target",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_evidence_confidence_range",
        ),
        sa.CheckConstraint(
            "classification <> 'FACT' OR confidence IS NULL",
            name="ck_evidence_fact_has_no_confidence",
        ),
        sa.CheckConstraint(
            "raw_payload_hash IS NULL OR raw_payload_hash ~ '^[a-f0-9]{64}$'",
            name="ck_evidence_raw_payload_hash",
        ),
    )
    op.create_index("ix_evidence_account_id", "evidence", ["account_id"])
    op.create_index("ix_evidence_strategy_version_id", "evidence", ["strategy_version_id"])


def downgrade() -> None:
    """Remove the M1A foundation without touching the M0 baseline marker."""

    op.drop_index("ix_evidence_strategy_version_id", table_name="evidence")
    op.drop_index("ix_evidence_account_id", table_name="evidence")
    op.drop_table("evidence")
    op.drop_table("accounts")
    op.drop_index("uq_strategy_versions_one_active_per_workspace", table_name="strategy_versions")
    op.drop_table("strategy_versions")
    op.drop_table("workspaces")
    strategy_topic.drop(op.get_bind(), checkfirst=True)
    evidence_freshness.drop(op.get_bind(), checkfirst=True)
    evidence_classification.drop(op.get_bind(), checkfirst=True)
    strategy_status.drop(op.get_bind(), checkfirst=True)
