"""Canonical persistence models for synthetic strategy, evidence, and signals."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import text

from gtm_state_api.types import (
    EvidenceAssertion,
    EvidenceClassification,
    EvidenceFreshness,
    SignalCategory,
    SignalDefinitionStatus,
    SignalEvaluationResult,
    SignalReasonCode,
    StrategyStatus,
    StrategyTopic,
)


class Base(DeclarativeBase):
    """Base class for canonical SQLAlchemy models."""


class Workspace(Base):
    """A minimal boundary for data owned by one GTM workspace."""

    __tablename__ = "workspaces"

    workspace_id: Mapped[UUID] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    demo_mode: Mapped[bool] = mapped_column(nullable=False, default=False)
    demo_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    strategy_versions: Mapped[list[StrategyVersion]] = relationship(back_populates="workspace")
    accounts: Mapped[list[Account]] = relationship(back_populates="workspace")


class StrategyVersion(Base):
    """An immutable-by-API version of a workspace's GTM strategy."""

    __tablename__ = "strategy_versions"
    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_strategy_versions_id_workspace"),
        Index(
            "uq_strategy_versions_one_active_per_workspace",
            "workspace_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.workspace_id", ondelete="RESTRICT")
    )
    semantic_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[StrategyStatus] = mapped_column(
        Enum(StrategyStatus, name="strategy_status", create_constraint=False), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    synthetic_disclaimer: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workspace: Mapped[Workspace] = relationship(back_populates="strategy_versions")
    evidence: Mapped[list[Evidence]] = relationship(back_populates="strategy_version")


class Account(Base):
    """Canonical synthetic account identity, without derived GTM state."""

    __tablename__ = "accounts"
    __table_args__ = (
        Index("uq_accounts_workspace_slug", "workspace_id", "slug", unique=True),
        Index("uq_accounts_workspace_domain", "workspace_id", "domain", unique=True),
        UniqueConstraint("id", "workspace_id", name="uq_accounts_id_workspace"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.workspace_id", ondelete="RESTRICT")
    )
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(200), nullable=False)
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    segment: Mapped[str] = mapped_column(String(160), nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    workspace: Mapped[Workspace] = relationship(back_populates="accounts")
    evidence: Mapped[list[Evidence]] = relationship(back_populates="account")


class Evidence(Base):
    """Provenance-bearing observation or strategy assertion for exactly one M1A target."""

    __tablename__ = "evidence"
    __table_args__ = (
        CheckConstraint(
            "(strategy_version_id IS NOT NULL AND account_id IS NULL) "
            "OR (strategy_version_id IS NULL AND account_id IS NOT NULL)",
            name="ck_evidence_exactly_one_target",
        ),
        CheckConstraint(
            "(strategy_version_id IS NOT NULL AND strategy_topic IS NOT NULL) "
            "OR (strategy_version_id IS NULL AND strategy_topic IS NULL)",
            name="ck_evidence_strategy_topic_matches_target",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_evidence_confidence_range",
        ),
        CheckConstraint(
            "classification <> 'FACT' OR confidence IS NULL",
            name="ck_evidence_fact_has_no_confidence",
        ),
        CheckConstraint(
            "raw_payload_hash IS NULL OR raw_payload_hash ~ '^[a-f0-9]{64}$'",
            name="ck_evidence_raw_payload_hash",
        ),
        CheckConstraint(
            "(fact_key IS NULL AND fact_assertion IS NULL) "
            "OR (fact_key IS NOT NULL AND fact_assertion IS NOT NULL)",
            name="ck_evidence_fact_shape",
        ),
        CheckConstraint(
            "fact_key IS NULL OR fact_key ~ '^[a-z][a-z0-9_.]*$'",
            name="ck_evidence_fact_key",
        ),
        UniqueConstraint("id", "account_id", name="uq_evidence_id_account"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    strategy_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="RESTRICT"), nullable=True
    )
    account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )
    strategy_topic: Mapped[StrategyTopic | None] = mapped_column(
        Enum(StrategyTopic, name="strategy_topic", create_constraint=False), nullable=True
    )
    classification: Mapped[EvidenceClassification] = mapped_column(
        Enum(EvidenceClassification, name="evidence_classification", create_constraint=False),
        nullable=False,
    )
    source_provider: Mapped[str] = mapped_column(String(120), nullable=False)
    source_reference: Mapped[str] = mapped_column(Text, nullable=False)
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    normalized_fact: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    freshness: Mapped[EvidenceFreshness] = mapped_column(
        Enum(EvidenceFreshness, name="evidence_freshness", create_constraint=False), nullable=False
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    fact_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    fact_assertion: Mapped[EvidenceAssertion | None] = mapped_column(
        Enum(EvidenceAssertion, name="evidence_assertion", create_constraint=False), nullable=True
    )

    strategy_version: Mapped[StrategyVersion | None] = relationship(back_populates="evidence")
    account: Mapped[Account | None] = relationship(back_populates="evidence")


class SignalDefinition(Base):
    """A strategy-aware immutable version of a deterministic signal rule."""

    __tablename__ = "signal_definitions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["strategy_version_id", "workspace_id"],
            ["strategy_versions.id", "strategy_versions.workspace_id"],
            name="fk_signal_definitions_strategy_workspace",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "workspace_id",
            "strategy_version_id",
            "stable_key",
            "rule_version",
            name="uq_signal_definitions_version",
        ),
        UniqueConstraint(
            "signal_definition_id",
            "workspace_id",
            "strategy_version_id",
            name="uq_signal_definitions_scope",
        ),
        CheckConstraint("freshness_window_days > 0", name="ck_signal_definition_freshness"),
        CheckConstraint("stable_key ~ '^[a-z][a-z0-9_]*$'", name="ck_signal_definition_stable_key"),
        CheckConstraint(
            "input_fact_key ~ '^[a-z][a-z0-9_.]*$'",
            name="ck_signal_definition_input_fact_key",
        ),
        CheckConstraint(
            "evaluator_key ~ '^[a-z][a-z0-9_]*$'",
            name="ck_signal_definition_evaluator_key",
        ),
        Index(
            "uq_signal_definitions_one_enabled",
            "strategy_version_id",
            "stable_key",
            unique=True,
            postgresql_where=text("status = 'ENABLED'"),
        ),
    )

    signal_definition_id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(nullable=False)
    strategy_version_id: Mapped[UUID] = mapped_column(nullable=False)
    stable_key: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[SignalCategory] = mapped_column(
        Enum(SignalCategory, name="signal_category", create_constraint=False), nullable=False
    )
    input_fact_key: Mapped[str] = mapped_column(String(160), nullable=False)
    evaluator_key: Mapped[str] = mapped_column(String(120), nullable=False)
    freshness_window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[SignalDefinitionStatus] = mapped_column(
        Enum(
            SignalDefinitionStatus,
            name="signal_definition_status",
            create_constraint=False,
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SignalEvaluation(Base):
    """An immutable deterministic conclusion at one semantic point in time."""

    __tablename__ = "signal_evaluations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "workspace_id"],
            ["accounts.id", "accounts.workspace_id"],
            name="fk_signal_evaluations_account_workspace",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["signal_definition_id", "workspace_id", "strategy_version_id"],
            [
                "signal_definitions.signal_definition_id",
                "signal_definitions.workspace_id",
                "signal_definitions.strategy_version_id",
            ],
            name="fk_signal_evaluations_definition_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "signal_id",
                "workspace_id",
                "account_id",
                "signal_definition_id",
                "strategy_version_id",
            ],
            [
                "signals.signal_id",
                "signals.workspace_id",
                "signals.account_id",
                "signals.signal_definition_id",
                "signals.strategy_version_id",
            ],
            name="fk_signal_evaluations_signal_scope",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        UniqueConstraint(
            "workspace_id",
            "account_id",
            "signal_definition_id",
            "strategy_version_id",
            "evaluation_as_of",
            "input_hash",
            name="uq_signal_evaluations_input",
        ),
        UniqueConstraint(
            "evaluation_id",
            "account_id",
            name="uq_signal_evaluations_id_account",
        ),
        UniqueConstraint(
            "evaluation_id",
            "workspace_id",
            "account_id",
            "signal_definition_id",
            "strategy_version_id",
            name="uq_signal_evaluations_scope",
        ),
        CheckConstraint("input_hash ~ '^[a-f0-9]{64}$'", name="ck_signal_evaluation_hash"),
    )

    evaluation_id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(nullable=False)
    account_id: Mapped[UUID] = mapped_column(nullable=False)
    signal_definition_id: Mapped[UUID] = mapped_column(nullable=False)
    strategy_version_id: Mapped[UUID] = mapped_column(nullable=False)
    signal_id: Mapped[UUID | None] = mapped_column(nullable=True)
    evaluation_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[SignalEvaluationResult] = mapped_column(
        Enum(SignalEvaluationResult, name="signal_evaluation_result", create_constraint=False),
        nullable=False,
    )
    reason_code: Mapped[SignalReasonCode] = mapped_column(
        Enum(SignalReasonCode, name="signal_reason_code", create_constraint=False), nullable=False
    )
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EvaluationEvidence(Base):
    """Relational provenance for every evidence record considered by an evaluation."""

    __tablename__ = "evaluation_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["evaluation_id", "account_id"],
            ["signal_evaluations.evaluation_id", "signal_evaluations.account_id"],
            name="fk_evaluation_evidence_evaluation_account",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["evidence_id", "account_id"],
            ["evidence.id", "evidence.account_id"],
            name="fk_evaluation_evidence_evidence_account",
            ondelete="RESTRICT",
        ),
    )

    evaluation_id: Mapped[UUID] = mapped_column(primary_key=True)
    evidence_id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column(nullable=False)


class Signal(Base):
    """A canonical commercial event whose identity excludes evaluation time."""

    __tablename__ = "signals"
    __table_args__ = (
        ForeignKeyConstraint(
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
        UniqueConstraint("event_fingerprint", name="uq_signals_event_fingerprint"),
        UniqueConstraint("origin_evaluation_id", name="uq_signals_origin_evaluation"),
        UniqueConstraint(
            "signal_id",
            "workspace_id",
            "account_id",
            "signal_definition_id",
            "strategy_version_id",
            name="uq_signals_scope",
        ),
        CheckConstraint(
            "event_fingerprint ~ '^[a-f0-9]{64}$'", name="ck_signals_event_fingerprint"
        ),
    )

    signal_id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(nullable=False)
    account_id: Mapped[UUID] = mapped_column(nullable=False)
    signal_definition_id: Mapped[UUID] = mapped_column(nullable=False)
    strategy_version_id: Mapped[UUID] = mapped_column(nullable=False)
    event_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    origin_evaluation_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
