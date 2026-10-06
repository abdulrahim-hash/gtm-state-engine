"""Canonical persistence models for synthetic strategy, evidence, and signals."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import text

from gtm_state_api.types import (
    AccountEvidenceSufficiency,
    AccountFitContext,
    AccountRelationshipState,
    AccountStateFacet,
    AccountStateReasonCode,
    AccountTimingState,
    ActionActorKind,
    ActionAttemptMode,
    ActionOutcomeReasonCode,
    ActionOutcomeResult,
    ActionReviewReasonCode,
    ActionReviewResolution,
    ActionType,
    DecisionReasonCode,
    DecisionResult,
    EvaluationDefinitionStatus,
    EvidenceAssertion,
    EvidenceClassification,
    EvidenceFreshness,
    EvidenceSupersessionReason,
    FitCriterionResult,
    IngestionReason,
    IngestionRowOutcome,
    NormalizationOutcome,
    PolicyReasonCode,
    PolicyResult,
    PolicyTarget,
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
    segment: Mapped[str | None] = mapped_column(String(160), nullable=True)
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
        ForeignKeyConstraint(
            ["normalization_result_id", "account_id"],
            ["normalization_results.id", "normalization_results.account_id"],
            name="fk_evidence_normalization_account",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("normalization_result_id", name="uq_evidence_normalization_result"),
        UniqueConstraint("id", "account_id", name="uq_evidence_id_account"),
        UniqueConstraint(
            "id",
            "strategy_version_id",
            name="uq_evidence_id_strategy_version",
        ),
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

    normalization_result_id: Mapped[UUID | None] = mapped_column(nullable=True)

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


class StrategyFitCriterion(Base):
    """Executable fit criterion justified by one synthetic strategy hypothesis."""

    __tablename__ = "strategy_fit_criteria"
    __table_args__ = (
        ForeignKeyConstraint(
            ["strategy_version_id", "workspace_id"],
            ["strategy_versions.id", "strategy_versions.workspace_id"],
            name="fk_strategy_fit_criteria_strategy_workspace",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_strategy_evidence_id", "strategy_version_id"],
            ["evidence.id", "evidence.strategy_version_id"],
            name="fk_strategy_fit_criteria_source_evidence",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "workspace_id",
            "strategy_version_id",
            "stable_key",
            name="uq_strategy_fit_criteria_stable_key",
        ),
        UniqueConstraint(
            "workspace_id",
            "strategy_version_id",
            "input_fact_key",
            name="uq_strategy_fit_criteria_fact_key",
        ),
        UniqueConstraint(
            "fit_criterion_id",
            "workspace_id",
            "strategy_version_id",
            name="uq_strategy_fit_criteria_scope",
        ),
        CheckConstraint(
            "stable_key ~ '^[a-z][a-z0-9_]*$'",
            name="ck_strategy_fit_criteria_stable_key",
        ),
        CheckConstraint(
            "input_fact_key ~ '^[a-z][a-z0-9_.]*$'",
            name="ck_strategy_fit_criteria_input_fact_key",
        ),
        CheckConstraint(
            "expected_assertion <> 'INCONCLUSIVE'",
            name="ck_strategy_fit_criteria_expected_assertion",
        ),
    )

    fit_criterion_id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(nullable=False)
    strategy_version_id: Mapped[UUID] = mapped_column(nullable=False)
    stable_key: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    input_fact_key: Mapped[str] = mapped_column(String(160), nullable=False)
    expected_assertion: Mapped[EvidenceAssertion] = mapped_column(
        Enum(EvidenceAssertion, name="evidence_assertion", create_constraint=False),
        nullable=False,
    )
    source_strategy_evidence_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AccountStateSnapshot(Base):
    """Immutable descriptive account state at one semantic point in time."""

    __tablename__ = "account_state_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "workspace_id"],
            ["accounts.id", "accounts.workspace_id"],
            name="fk_account_state_snapshots_account_workspace",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["strategy_version_id", "workspace_id"],
            ["strategy_versions.id", "strategy_versions.workspace_id"],
            name="fk_account_state_snapshots_strategy_workspace",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "workspace_id",
            "account_id",
            "strategy_version_id",
            "state_as_of",
            "state_engine_version",
            "input_hash",
            name="uq_account_state_snapshots_semantic_input",
        ),
        UniqueConstraint(
            "state_snapshot_id",
            "account_id",
            name="uq_account_state_snapshots_id_account",
        ),
        UniqueConstraint(
            "state_snapshot_id",
            "workspace_id",
            "account_id",
            "strategy_version_id",
            name="uq_account_state_snapshots_scope",
        ),
        CheckConstraint(
            "input_hash ~ '^[a-f0-9]{64}$'",
            name="ck_account_state_snapshots_input_hash",
        ),
    )

    state_snapshot_id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(nullable=False)
    account_id: Mapped[UUID] = mapped_column(nullable=False)
    strategy_version_id: Mapped[UUID] = mapped_column(nullable=False)
    state_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state_engine_version: Mapped[str] = mapped_column(String(32), nullable=False)
    fit_context: Mapped[AccountFitContext] = mapped_column(
        Enum(AccountFitContext, name="account_fit_context", create_constraint=False),
        nullable=False,
    )
    timing_state: Mapped[AccountTimingState] = mapped_column(
        Enum(AccountTimingState, name="account_timing_state", create_constraint=False),
        nullable=False,
    )
    relationship_state: Mapped[AccountRelationshipState] = mapped_column(
        Enum(
            AccountRelationshipState,
            name="account_relationship_state",
            create_constraint=False,
        ),
        nullable=False,
    )
    evidence_sufficiency: Mapped[AccountEvidenceSufficiency] = mapped_column(
        Enum(
            AccountEvidenceSufficiency,
            name="account_evidence_sufficiency",
            create_constraint=False,
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StateSnapshotReason(Base):
    """Ordered, facet-scoped explanation for one state snapshot."""

    __tablename__ = "state_snapshot_reasons"
    __table_args__ = (
        UniqueConstraint(
            "state_snapshot_id",
            "facet",
            "reason_code",
            name="uq_state_snapshot_reasons_code",
        ),
        CheckConstraint("position >= 0", name="ck_state_snapshot_reasons_position"),
    )

    state_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("account_state_snapshots.state_snapshot_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    facet: Mapped[AccountStateFacet] = mapped_column(
        Enum(AccountStateFacet, name="account_state_facet", create_constraint=False),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    reason_code: Mapped[AccountStateReasonCode] = mapped_column(
        Enum(
            AccountStateReasonCode,
            name="account_state_reason_code",
            create_constraint=False,
        ),
        nullable=False,
    )


class StateSnapshotFitCriterion(Base):
    """Frozen per-criterion interpretation for exact historical fit provenance."""

    __tablename__ = "state_snapshot_fit_criteria"
    __table_args__ = (
        ForeignKeyConstraint(
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
        ForeignKeyConstraint(
            ["fit_criterion_id", "workspace_id", "strategy_version_id"],
            [
                "strategy_fit_criteria.fit_criterion_id",
                "strategy_fit_criteria.workspace_id",
                "strategy_fit_criteria.strategy_version_id",
            ],
            name="fk_state_snapshot_fit_criteria_criterion_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_strategy_evidence_id", "strategy_version_id"],
            ["evidence.id", "evidence.strategy_version_id"],
            name="fk_state_snapshot_fit_criteria_source_evidence",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "state_snapshot_id",
            "fit_criterion_id",
            name="uq_state_snapshot_fit_criteria_link",
        ),
    )

    state_snapshot_id: Mapped[UUID] = mapped_column(primary_key=True)
    fit_criterion_id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(nullable=False)
    account_id: Mapped[UUID] = mapped_column(nullable=False)
    strategy_version_id: Mapped[UUID] = mapped_column(nullable=False)
    criterion_stable_key: Mapped[str] = mapped_column(String(120), nullable=False)
    input_fact_key: Mapped[str] = mapped_column(String(160), nullable=False)
    source_strategy_evidence_id: Mapped[UUID] = mapped_column(nullable=False)
    expected_assertion: Mapped[EvidenceAssertion] = mapped_column(
        Enum(EvidenceAssertion, name="evidence_assertion", create_constraint=False),
        nullable=False,
    )
    observed_assertion: Mapped[EvidenceAssertion | None] = mapped_column(
        Enum(EvidenceAssertion, name="evidence_assertion", create_constraint=False),
        nullable=True,
    )
    criterion_result: Mapped[FitCriterionResult] = mapped_column(
        Enum(FitCriterionResult, name="fit_criterion_result", create_constraint=False),
        nullable=False,
    )


class StateSnapshotEvidence(Base):
    """Direct fit or relationship evidence considered by a snapshot."""

    __tablename__ = "state_snapshot_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["state_snapshot_id", "account_id"],
            ["account_state_snapshots.state_snapshot_id", "account_state_snapshots.account_id"],
            name="fk_state_snapshot_evidence_snapshot_account",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["evidence_id", "account_id"],
            ["evidence.id", "evidence.account_id"],
            name="fk_state_snapshot_evidence_evidence_account",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["state_snapshot_id", "fit_criterion_id"],
            [
                "state_snapshot_fit_criteria.state_snapshot_id",
                "state_snapshot_fit_criteria.fit_criterion_id",
            ],
            name="fk_state_snapshot_evidence_fit_criterion",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(facet = 'FIT_CONTEXT' AND fit_criterion_id IS NOT NULL) "
            "OR (facet = 'RELATIONSHIP_STATE' AND fit_criterion_id IS NULL)",
            name="ck_state_snapshot_evidence_facet_shape",
        ),
    )

    state_snapshot_id: Mapped[UUID] = mapped_column(primary_key=True)
    evidence_id: Mapped[UUID] = mapped_column(primary_key=True)
    facet: Mapped[AccountStateFacet] = mapped_column(
        Enum(AccountStateFacet, name="account_state_facet", create_constraint=False),
        primary_key=True,
    )
    account_id: Mapped[UUID] = mapped_column(nullable=False)
    fit_criterion_id: Mapped[UUID | None] = mapped_column(nullable=True)


class StateSnapshotSignalEvaluation(Base):
    """Same-time signal evaluation used by a timing-state conclusion."""

    __tablename__ = "state_snapshot_signal_evaluations"
    __table_args__ = (
        ForeignKeyConstraint(
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
        ForeignKeyConstraint(
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

    state_snapshot_id: Mapped[UUID] = mapped_column(primary_key=True)
    evaluation_id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(nullable=False)
    account_id: Mapped[UUID] = mapped_column(nullable=False)
    strategy_version_id: Mapped[UUID] = mapped_column(nullable=False)
    signal_definition_id: Mapped[UUID] = mapped_column(nullable=False)


class DecisionDefinition(Base):
    """Immutable version selecting one code-owned Decision evaluator."""

    __tablename__ = "decision_definitions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["strategy_version_id", "workspace_id"],
            ["strategy_versions.id", "strategy_versions.workspace_id"],
            name="fk_decision_definitions_strategy_workspace",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "workspace_id",
            "strategy_version_id",
            "stable_key",
            "definition_version",
            name="uq_decision_definitions_version",
        ),
        UniqueConstraint(
            "decision_definition_id",
            "workspace_id",
            "strategy_version_id",
            "definition_version",
            name="uq_decision_definitions_scope",
        ),
        CheckConstraint(
            "stable_key ~ '^[a-z][a-z0-9_]*$'",
            name="ck_decision_definitions_stable_key",
        ),
        CheckConstraint(
            "evaluator_key ~ '^[a-z][a-z0-9_]*$'",
            name="ck_decision_definitions_evaluator_key",
        ),
        Index(
            "uq_decision_definitions_one_enabled",
            "workspace_id",
            "strategy_version_id",
            unique=True,
            postgresql_where=text("status = 'ENABLED'"),
        ),
    )

    decision_definition_id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(nullable=False)
    strategy_version_id: Mapped[UUID] = mapped_column(nullable=False)
    stable_key: Mapped[str] = mapped_column(String(120), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evaluator_key: Mapped[str] = mapped_column(String(120), nullable=False)
    evaluator_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[EvaluationDefinitionStatus] = mapped_column(
        Enum(
            EvaluationDefinitionStatus,
            name="evaluation_definition_status",
            create_constraint=False,
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DecisionEvaluation(Base):
    """Immutable Decision result attesting to one complete state snapshot."""

    __tablename__ = "decision_evaluations"
    __table_args__ = (
        ForeignKeyConstraint(
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
        ForeignKeyConstraint(
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
        UniqueConstraint(
            "state_snapshot_id",
            "decision_definition_id",
            name="uq_decision_evaluations_snapshot_definition",
        ),
        UniqueConstraint(
            "decision_evaluation_id",
            "workspace_id",
            "account_id",
            "strategy_version_id",
            "state_snapshot_id",
            name="uq_decision_evaluations_scope",
        ),
        CheckConstraint(
            "input_hash ~ '^[a-f0-9]{64}$'",
            name="ck_decision_evaluations_input_hash",
        ),
        Index(
            "ix_decision_evaluations_account_history",
            "workspace_id",
            "account_id",
            "strategy_version_id",
            "evaluated_at",
        ),
    )

    decision_evaluation_id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(nullable=False)
    account_id: Mapped[UUID] = mapped_column(nullable=False)
    strategy_version_id: Mapped[UUID] = mapped_column(nullable=False)
    state_snapshot_id: Mapped[UUID] = mapped_column(nullable=False)
    decision_definition_id: Mapped[UUID] = mapped_column(nullable=False)
    definition_version: Mapped[str] = mapped_column(String(32), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[DecisionResult] = mapped_column(
        Enum(DecisionResult, name="decision_result", create_constraint=False), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DecisionEvaluationReason(Base):
    """Ordered deterministic reason for one Decision evaluation."""

    __tablename__ = "decision_evaluation_reasons"
    __table_args__ = (
        UniqueConstraint(
            "decision_evaluation_id",
            "reason_code",
            name="uq_decision_evaluation_reasons_code",
        ),
        CheckConstraint("position >= 0", name="ck_decision_evaluation_reasons_position"),
    )

    decision_evaluation_id: Mapped[UUID] = mapped_column(
        ForeignKey("decision_evaluations.decision_evaluation_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    reason_code: Mapped[DecisionReasonCode] = mapped_column(
        Enum(DecisionReasonCode, name="decision_reason_code", create_constraint=False),
        nullable=False,
    )


class PolicyDefinition(Base):
    """Immutable version selecting one code-owned Policy evaluator."""

    __tablename__ = "policy_definitions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["strategy_version_id", "workspace_id"],
            ["strategy_versions.id", "strategy_versions.workspace_id"],
            name="fk_policy_definitions_strategy_workspace",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "workspace_id",
            "strategy_version_id",
            "stable_key",
            "definition_version",
            name="uq_policy_definitions_version",
        ),
        UniqueConstraint(
            "policy_definition_id",
            "workspace_id",
            "strategy_version_id",
            "definition_version",
            name="uq_policy_definitions_scope",
        ),
        CheckConstraint(
            "stable_key ~ '^[a-z][a-z0-9_]*$'",
            name="ck_policy_definitions_stable_key",
        ),
        CheckConstraint(
            "evaluator_key ~ '^[a-z][a-z0-9_]*$'",
            name="ck_policy_definitions_evaluator_key",
        ),
        Index(
            "uq_policy_definitions_one_enabled",
            "workspace_id",
            "strategy_version_id",
            "target",
            unique=True,
            postgresql_where=text("status = 'ENABLED'"),
        ),
    )

    policy_definition_id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(nullable=False)
    strategy_version_id: Mapped[UUID] = mapped_column(nullable=False)
    stable_key: Mapped[str] = mapped_column(String(120), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[PolicyTarget] = mapped_column(
        Enum(PolicyTarget, name="policy_target", create_constraint=False), nullable=False
    )
    evaluator_key: Mapped[str] = mapped_column(String(120), nullable=False)
    evaluator_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[EvaluationDefinitionStatus] = mapped_column(
        Enum(
            EvaluationDefinitionStatus,
            name="evaluation_definition_status",
            create_constraint=False,
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PolicyEvaluation(Base):
    """Immutable Policy gate for one Decision and the exact same state snapshot."""

    __tablename__ = "policy_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "policy_evaluation_id",
            "workspace_id",
            "account_id",
            "strategy_version_id",
            name="uq_policy_evaluations_action_scope",
        ),
        ForeignKeyConstraint(
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
        ForeignKeyConstraint(
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
        ForeignKeyConstraint(
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
        UniqueConstraint(
            "decision_evaluation_id",
            "policy_definition_id",
            name="uq_policy_evaluations_decision_definition",
        ),
        CheckConstraint(
            "input_hash ~ '^[a-f0-9]{64}$'",
            name="ck_policy_evaluations_input_hash",
        ),
        Index("ix_policy_evaluations_decision", "decision_evaluation_id"),
    )

    policy_evaluation_id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(nullable=False)
    account_id: Mapped[UUID] = mapped_column(nullable=False)
    strategy_version_id: Mapped[UUID] = mapped_column(nullable=False)
    state_snapshot_id: Mapped[UUID] = mapped_column(nullable=False)
    decision_evaluation_id: Mapped[UUID] = mapped_column(nullable=False)
    policy_definition_id: Mapped[UUID] = mapped_column(nullable=False)
    definition_version: Mapped[str] = mapped_column(String(32), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[PolicyResult] = mapped_column(
        Enum(PolicyResult, name="policy_result", create_constraint=False), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Action(Base):
    """Immutable vendor-neutral GTM operational intent."""

    __tablename__ = "actions"
    __table_args__ = (
        ForeignKeyConstraint(
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
        UniqueConstraint(
            "policy_evaluation_id",
            "derivation_key",
            "derivation_version",
            name="uq_actions_policy_derivation",
        ),
        UniqueConstraint("semantic_input_hash", name="uq_actions_semantic_input_hash"),
        UniqueConstraint("action_id", "workspace_id", "account_id", name="uq_actions_scope"),
        CheckConstraint(
            "semantic_input_hash ~ '^[a-f0-9]{64}$'",
            name="ck_actions_semantic_input_hash",
        ),
        CheckConstraint(
            "jsonb_typeof(payload) = 'object'",
            name="ck_actions_payload_object",
        ),
        Index(
            "ix_actions_account_history",
            "workspace_id",
            "account_id",
            "proposed_at",
        ),
        Index("ix_actions_policy_evaluation", "policy_evaluation_id"),
    )

    action_id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(nullable=False)
    account_id: Mapped[UUID] = mapped_column(nullable=False)
    strategy_version_id: Mapped[UUID] = mapped_column(nullable=False)
    policy_evaluation_id: Mapped[UUID] = mapped_column(nullable=False)
    action_type: Mapped[ActionType] = mapped_column(
        Enum(ActionType, name="action_type", create_constraint=False),
        nullable=False,
    )
    action_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    derivation_key: Mapped[str] = mapped_column(String(120), nullable=False)
    derivation_version: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    semantic_input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    proposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ActionReview(Base):
    """One immutable terminal review of a review-required Action proposal."""

    __tablename__ = "action_reviews"
    __table_args__ = (
        UniqueConstraint("action_id", name="uq_action_reviews_one_terminal"),
        UniqueConstraint(
            "action_id",
            "idempotency_key_hash",
            name="uq_action_reviews_idempotency",
        ),
        UniqueConstraint("review_id", "action_id", name="uq_action_reviews_scope"),
        CheckConstraint(
            "idempotency_key_hash ~ '^[a-f0-9]{64}$'",
            name="ck_action_reviews_idempotency_hash",
        ),
        CheckConstraint(
            "request_hash ~ '^[a-f0-9]{64}$'",
            name="ck_action_reviews_request_hash",
        ),
    )

    review_id: Mapped[UUID] = mapped_column(primary_key=True)
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("actions.action_id", ondelete="RESTRICT"),
        nullable=False,
    )
    resolution: Mapped[ActionReviewResolution] = mapped_column(
        Enum(
            ActionReviewResolution,
            name="action_review_resolution",
            create_constraint=False,
        ),
        nullable=False,
    )
    reason_code: Mapped[ActionReviewReasonCode] = mapped_column(
        Enum(
            ActionReviewReasonCode,
            name="action_review_reason_code",
            create_constraint=False,
        ),
        nullable=False,
    )
    reviewer_kind: Mapped[ActionActorKind] = mapped_column(
        Enum(ActionActorKind, name="action_actor_kind", create_constraint=False),
        nullable=False,
    )
    reviewer_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ActionAttempt(Base):
    """Immutable local validation attempt; M1D never executes externally."""

    __tablename__ = "action_attempts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["review_id", "action_id"],
            ["action_reviews.review_id", "action_reviews.action_id"],
            name="fk_action_attempts_review_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "action_id",
            "mode",
            "validator_key",
            "validator_version",
            "input_hash",
            name="uq_action_attempts_semantic",
        ),
        UniqueConstraint(
            "action_attempt_id",
            "action_id",
            name="uq_action_attempts_scope",
        ),
        CheckConstraint(
            "input_hash ~ '^[a-f0-9]{64}$'",
            name="ck_action_attempts_input_hash",
        ),
        Index("ix_action_attempts_action", "action_id", "attempted_at"),
    )

    action_attempt_id: Mapped[UUID] = mapped_column(primary_key=True)
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("actions.action_id", ondelete="RESTRICT"),
        nullable=False,
    )
    review_id: Mapped[UUID | None] = mapped_column(nullable=True)
    mode: Mapped[ActionAttemptMode] = mapped_column(
        Enum(ActionAttemptMode, name="action_attempt_mode", create_constraint=False),
        nullable=False,
    )
    validator_key: Mapped[str] = mapped_column(String(120), nullable=False)
    validator_version: Mapped[str] = mapped_column(String(32), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by_kind: Mapped[ActionActorKind] = mapped_column(
        Enum(ActionActorKind, name="action_actor_kind", create_constraint=False),
        nullable=False,
    )
    requested_by_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ActionOutcome(Base):
    """Immutable operational result of one local dry-run attempt."""

    __tablename__ = "action_outcomes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["action_attempt_id", "action_id"],
            ["action_attempts.action_attempt_id", "action_attempts.action_id"],
            name="fk_action_outcomes_attempt_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "action_attempt_id",
            name="uq_action_outcomes_one_per_attempt",
        ),
        CheckConstraint(
            "result_hash ~ '^[a-f0-9]{64}$'",
            name="ck_action_outcomes_result_hash",
        ),
        CheckConstraint(
            "external_side_effects = false",
            name="ck_action_outcomes_no_external_side_effects",
        ),
        Index("ix_action_outcomes_action", "action_id", "observed_at"),
    )

    outcome_id: Mapped[UUID] = mapped_column(primary_key=True)
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("actions.action_id", ondelete="RESTRICT"),
        nullable=False,
    )
    action_attempt_id: Mapped[UUID] = mapped_column(nullable=False)
    result: Mapped[ActionOutcomeResult] = mapped_column(
        Enum(ActionOutcomeResult, name="action_outcome_result", create_constraint=False),
        nullable=False,
    )
    reason_code: Mapped[ActionOutcomeReasonCode] = mapped_column(
        Enum(
            ActionOutcomeReasonCode,
            name="action_outcome_reason_code",
            create_constraint=False,
        ),
        nullable=False,
    )
    outcome_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    external_side_effects: Mapped[bool] = mapped_column(nullable=False, default=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PolicyEvaluationReason(Base):
    """Ordered deterministic reason for one Policy evaluation."""

    __tablename__ = "policy_evaluation_reasons"
    __table_args__ = (
        UniqueConstraint(
            "policy_evaluation_id",
            "reason_code",
            name="uq_policy_evaluation_reasons_code",
        ),
        CheckConstraint("position >= 0", name="ck_policy_evaluation_reasons_position"),
    )

    policy_evaluation_id: Mapped[UUID] = mapped_column(
        ForeignKey("policy_evaluations.policy_evaluation_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    reason_code: Mapped[PolicyReasonCode] = mapped_column(
        Enum(PolicyReasonCode, name="policy_reason_code", create_constraint=False),
        nullable=False,
    )


class IngestionBatch(Base):
    """One exact bounded source file in a workspace."""

    __tablename__ = "ingestion_batches"
    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_ingestion_batches_scope"),
        UniqueConstraint(
            "id",
            "workspace_id",
            "source_system_key",
            "dataset_key",
            name="uq_ingestion_batches_source_scope",
        ),
        UniqueConstraint(
            "workspace_id",
            "source_system_key",
            "dataset_key",
            "schema_key",
            "schema_version",
            "file_sha256",
            name="uq_ingestion_batches_semantic",
        ),
        CheckConstraint("expected_rows BETWEEN 1 AND 500", name="ck_ingestion_batches_rows"),
        CheckConstraint("file_sha256 ~ '^[a-f0-9]{64}$'", name="ck_ingestion_batches_hash"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.workspace_id", ondelete="RESTRICT")
    )
    source_system_key: Mapped[str] = mapped_column(String(80), nullable=False)
    dataset_key: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_key: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    mapper_key: Mapped[str] = mapped_column(String(80), nullable=False)
    mapper_version: Mapped[str] = mapped_column(String(32), nullable=False)
    identity_rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(nullable=False)
    expected_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SourceReadRun(Base):
    """One local, bounded private-provider read; never an Action outcome."""

    __tablename__ = "source_read_runs"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "workspace_id",
            "source_system_key",
            "dataset_key",
            name="uq_source_read_runs_scope",
        ),
        CheckConstraint("scope_sha256 ~ '^[a-f0-9]{64}$'", name="ck_source_read_runs_scope_hash"),
        CheckConstraint(
            "request_sha256 ~ '^[a-f0-9]{64}$'", name="ck_source_read_runs_request_hash"
        ),
        CheckConstraint(
            "status IN ('RUNNING', 'SUCCEEDED', 'NOT_FOUND', 'UNRESOLVED', "
            "'REJECTED', 'CONFLICT', 'FAILED')",
            name="ck_source_read_runs_status",
        ),
        CheckConstraint(
            "accepted_count BETWEEN 0 AND 1 AND unresolved_count BETWEEN 0 AND 1 "
            "AND rejected_count BETWEEN 0 AND 1 AND retry_count BETWEEN 0 AND 2",
            name="ck_source_read_runs_counts",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"), nullable=False
    )
    source_system_key: Mapped[str] = mapped_column(String(80), nullable=False)
    dataset_key: Mapped[str] = mapped_column(String(80), nullable=False)
    adapter_key: Mapped[str] = mapped_column(String(80), nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(32), nullable=False)
    mapping_version: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    response_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unresolved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    provider_correlation_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    observation_id: Mapped[UUID | None] = mapped_column(nullable=True)


class SourceObservation(Base):
    """Deduplicated version of a source record, independent of Account resolution."""

    __tablename__ = "source_observations"
    __table_args__ = (
        ForeignKeyConstraint(
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
        ForeignKeyConstraint(
            ["source_read_run_id", "workspace_id", "source_system_key", "dataset_key"],
            [
                "source_read_runs.id",
                "source_read_runs.workspace_id",
                "source_read_runs.source_system_key",
                "source_read_runs.dataset_key",
            ],
            name="fk_source_observations_read_run_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(first_batch_id IS NOT NULL) <> (source_read_run_id IS NOT NULL)",
            name="ck_source_observations_one_origin",
        ),
        UniqueConstraint("id", "workspace_id", name="uq_source_observations_scope"),
        UniqueConstraint(
            "id",
            "workspace_id",
            "source_system_key",
            "dataset_key",
            name="uq_source_observations_source_scope",
        ),
        UniqueConstraint(
            "workspace_id",
            "source_system_key",
            "dataset_key",
            "external_record_id",
            "source_observed_at",
            "payload_sha256",
            name="uq_source_observations_semantic",
        ),
        CheckConstraint("payload_sha256 ~ '^[a-f0-9]{64}$'", name="ck_source_observations_hash"),
        CheckConstraint(
            "jsonb_typeof(original_fields) = 'object' "
            "AND octet_length(original_fields::text) <= 4096",
            name="ck_source_observations_fields",
        ),
        CheckConstraint("first_row_ordinal > 0", name="ck_source_observations_ordinal"),
        Index(
            "ix_source_observations_record_time",
            "workspace_id",
            "source_system_key",
            "dataset_key",
            "external_record_id",
            "source_observed_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(nullable=False)
    source_system_key: Mapped[str] = mapped_column(String(80), nullable=False)
    dataset_key: Mapped[str] = mapped_column(String(80), nullable=False)
    external_record_id: Mapped[str] = mapped_column(String(120), nullable=False)
    external_account_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    original_fields: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    first_batch_id: Mapped[UUID | None] = mapped_column(nullable=True)
    source_read_run_id: Mapped[UUID | None] = mapped_column(nullable=True)
    first_row_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AccountSourceId(Base):
    """Immutable source-scoped binding, never a canonical Account identity."""

    __tablename__ = "account_source_ids"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "workspace_id"],
            ["accounts.id", "accounts.workspace_id"],
            name="fk_account_source_ids_account_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
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
        UniqueConstraint(
            "workspace_id",
            "source_system_key",
            "dataset_key",
            "external_account_id",
            name="uq_account_source_ids_external",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(nullable=False)
    source_system_key: Mapped[str] = mapped_column(String(80), nullable=False)
    dataset_key: Mapped[str] = mapped_column(String(80), nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(120), nullable=False)
    account_id: Mapped[UUID] = mapped_column(nullable=False)
    origin_observation_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NormalizationResult(Base):
    """One immutable code-versioned interpretation of a source observation."""

    __tablename__ = "normalization_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_observation_id", "workspace_id"],
            ["source_observations.id", "source_observations.workspace_id"],
            name="fk_normalization_results_observation_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["account_id", "workspace_id"],
            ["accounts.id", "accounts.workspace_id"],
            name="fk_normalization_results_account_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "source_observation_id",
            "mapper_key",
            "mapper_version",
            "identity_rule_version",
            name="uq_normalization_results_version",
        ),
        UniqueConstraint("id", "account_id", name="uq_normalization_results_evidence_scope"),
        CheckConstraint(
            "output_sha256 IS NULL OR output_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_normalization_results_hash",
        ),
        CheckConstraint(
            "resolution_input_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_normalization_results_resolution_hash",
        ),
        CheckConstraint(
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

    id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(nullable=False)
    source_observation_id: Mapped[UUID] = mapped_column(nullable=False)
    mapper_key: Mapped[str] = mapped_column(String(80), nullable=False)
    mapper_version: Mapped[str] = mapped_column(String(32), nullable=False)
    identity_rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    output_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[NormalizationOutcome] = mapped_column(
        Enum(NormalizationOutcome, name="normalization_outcome", create_constraint=False),
        nullable=False,
    )
    reason_code: Mapped[IngestionReason | None] = mapped_column(
        Enum(IngestionReason, name="ingestion_reason", create_constraint=False),
        nullable=True,
    )
    account_id: Mapped[UUID | None] = mapped_column(nullable=True)
    fact_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    fact_assertion: Mapped[str | None] = mapped_column(String(16), nullable=True)
    evidence_classification: Mapped[str | None] = mapped_column(String(16), nullable=True)
    normalized_fact: Mapped[str | None] = mapped_column(String(500), nullable=True)
    fact_observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    output_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolution_input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IngestionBatchRow(Base):
    """An immutable occurrence of a source record in one batch."""

    __tablename__ = "ingestion_batch_rows"
    __table_args__ = (
        UniqueConstraint("batch_id", "ordinal", name="uq_ingestion_batch_rows_ordinal"),
        CheckConstraint("ordinal > 0", name="ck_ingestion_batch_rows_ordinal"),
        CheckConstraint("row_sha256 ~ '^[a-f0-9]{64}$'", name="ck_ingestion_batch_rows_hash"),
        CheckConstraint(
            "(outcome = 'ACCEPTED' AND normalization_result_id IS NOT NULL "
            "AND reason_code IS NULL) "
            "OR (outcome <> 'ACCEPTED' AND reason_code IS NOT NULL)",
            name="ck_ingestion_batch_rows_outcome_shape",
        ),
        Index("ix_ingestion_batch_rows_batch", "batch_id", "ordinal"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    batch_id: Mapped[UUID] = mapped_column(ForeignKey("ingestion_batches.id", ondelete="RESTRICT"))
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    row_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[IngestionRowOutcome] = mapped_column(
        Enum(IngestionRowOutcome, name="ingestion_row_outcome", create_constraint=False),
        nullable=False,
    )
    reason_code: Mapped[IngestionReason | None] = mapped_column(
        Enum(IngestionReason, name="ingestion_reason", create_constraint=False),
        nullable=True,
    )
    source_observation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_observations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    normalization_result_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("normalization_results.id", ondelete="RESTRICT"),
        nullable=True,
    )
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EvidenceSupersession(Base):
    """An explicit promotion that replaces one imported Evidence in new computations."""

    __tablename__ = "evidence_supersessions"
    __table_args__ = (
        UniqueConstraint("old_evidence_id", name="uq_evidence_supersessions_old"),
        UniqueConstraint("new_evidence_id", name="uq_evidence_supersessions_new"),
        CheckConstraint(
            "old_evidence_id <> new_evidence_id", name="ck_evidence_supersessions_distinct"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    old_evidence_id: Mapped[UUID] = mapped_column(ForeignKey("evidence.id", ondelete="RESTRICT"))
    new_evidence_id: Mapped[UUID] = mapped_column(ForeignKey("evidence.id", ondelete="RESTRICT"))
    reason: Mapped[EvidenceSupersessionReason] = mapped_column(
        Enum(
            EvidenceSupersessionReason, name="evidence_supersession_reason", create_constraint=False
        ),
        nullable=False,
    )
    promoted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ExecutionPlan(Base):
    """Immutable provider-scoped translation of one canonical Action."""

    __tablename__ = "execution_plans"
    __table_args__ = (
        UniqueConstraint("plan_hash", name="uq_execution_plans_hash"),
        UniqueConstraint("marker", name="uq_execution_plans_marker"),
        UniqueConstraint("id", "action_id", name="uq_execution_plans_action_scope"),
        ForeignKeyConstraint(
            ["action_id", "workspace_id", "account_id"],
            ["actions.action_id", "actions.workspace_id", "actions.account_id"],
            name="fk_execution_plans_action_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint("plan_hash ~ '^[a-f0-9]{64}$'", name="ck_execution_plans_hash"),
        CheckConstraint(
            "portal_scope_hash ~ '^[a-f0-9]{64}$'", name="ck_execution_plans_portal_hash"
        ),
        CheckConstraint("operation = 'CREATE_SELLER_TASK'", name="ck_execution_plans_operation"),
        CheckConstraint(
            "jsonb_typeof(task_fields) = 'object'", name="ck_execution_plans_task_object"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    action_id: Mapped[UUID] = mapped_column(ForeignKey("actions.action_id", ondelete="RESTRICT"))
    action_hash: Mapped[str] = mapped_column(String(64))
    policy_evaluation_id: Mapped[UUID] = mapped_column()
    policy_hash: Mapped[str] = mapped_column(String(64))
    decision_evaluation_id: Mapped[UUID] = mapped_column()
    state_snapshot_id: Mapped[UUID] = mapped_column()
    workspace_id: Mapped[UUID] = mapped_column()
    account_id: Mapped[UUID] = mapped_column()
    adapter_key: Mapped[str] = mapped_column(String(80))
    adapter_version: Mapped[str] = mapped_column(String(32))
    api_version: Mapped[str] = mapped_column(String(16))
    operation: Mapped[str] = mapped_column(String(40))
    portal_scope_hash: Mapped[str] = mapped_column(String(64))
    provider_company_id: Mapped[str] = mapped_column(String(30))
    provider_owner_id: Mapped[str] = mapped_column(String(30))
    association_type_id: Mapped[int] = mapped_column(Integer)
    task_fields: Mapped[dict[str, str]] = mapped_column(JSONB)
    marker: Mapped[str] = mapped_column(String(40))
    schema_version: Mapped[str] = mapped_column(String(16))
    plan_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExecutionAuthorization(Base):
    """Local attestation for one exact provider plan, distinct from M1D Review."""

    __tablename__ = "execution_authorizations"
    __table_args__ = (
        UniqueConstraint("execution_plan_id", name="uq_execution_authorizations_plan"),
        UniqueConstraint("id", "execution_plan_id", name="uq_execution_authorizations_plan_scope"),
        ForeignKeyConstraint(
            ["execution_plan_id", "action_id"],
            ["execution_plans.id", "execution_plans.action_id"],
            name="fk_execution_authorizations_plan_action",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "assurance_type = 'LOCAL_OPERATOR_ATTESTATION'",
            name="ck_execution_authorizations_assurance",
        ),
        CheckConstraint(
            "status IN ('ACTIVE','REVOKED')", name="ck_execution_authorizations_status"
        ),
        CheckConstraint("expires_at > authorized_at", name="ck_execution_authorizations_expiry"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    execution_plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_plans.id", ondelete="RESTRICT")
    )
    action_id: Mapped[UUID] = mapped_column()
    action_hash: Mapped[str] = mapped_column(String(64))
    plan_hash: Mapped[str] = mapped_column(String(64))
    portal_scope_hash: Mapped[str] = mapped_column(String(64))
    provider_company_id: Mapped[str] = mapped_column(String(30))
    provider_owner_id: Mapped[str] = mapped_column(String(30))
    operation: Mapped[str] = mapped_column(String(40))
    assurance_type: Mapped[str] = mapped_column(String(40))
    operator_ref: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16))
    authorized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExecutionAttempt(Base):
    """Durable intent and conservative one-dispatch state."""

    __tablename__ = "execution_attempts"
    __table_args__ = (
        UniqueConstraint("execution_plan_id", name="uq_execution_attempts_plan"),
        UniqueConstraint("action_id", name="uq_execution_attempts_action_one_delivery"),
        UniqueConstraint("authorization_id", name="uq_execution_attempts_authorization"),
        ForeignKeyConstraint(
            ["execution_plan_id", "action_id"],
            ["execution_plans.id", "execution_plans.action_id"],
            name="fk_execution_attempts_plan_action",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["authorization_id", "execution_plan_id"],
            ["execution_authorizations.id", "execution_authorizations.execution_plan_id"],
            name="fk_execution_attempts_authorization_plan",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "physical_post_count BETWEEN 0 AND 1", name="ck_execution_attempts_one_post"
        ),
        CheckConstraint(
            "delivery_duration_ms IS NULL OR delivery_duration_ms >= 0",
            name="ck_execution_attempts_duration",
        ),
        CheckConstraint(
            """status IN (
                'NOT_ATTEMPTED','IN_FLIGHT','PROVIDER_ACCEPTED','CONFIRMED',
                'REJECTED_NO_WRITE','UNKNOWN_DELIVERY','MISMATCH'
            )""",
            name="ck_execution_attempts_status",
        ),
        CheckConstraint(
            """(status = 'NOT_ATTEMPTED' AND physical_post_count = 0) OR
               (status <> 'NOT_ATTEMPTED' AND physical_post_count = 1)""",
            name="ck_execution_attempts_dispatch_count",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    execution_plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_plans.id", ondelete="RESTRICT")
    )
    action_id: Mapped[UUID] = mapped_column()
    authorization_id: Mapped[UUID] = mapped_column()
    status: Mapped[str] = mapped_column(String(24))
    dispatch_id: Mapped[UUID | None] = mapped_column(unique=True)
    physical_post_count: Mapped[int] = mapped_column(Integer)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    safe_correlation: Mapped[str | None] = mapped_column(String(120))
    delivery_duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExecutionAttemptEvent(Base):
    """Append-only audit of every external-attempt state transition."""

    __tablename__ = "execution_attempt_events"
    __table_args__ = (
        UniqueConstraint(
            "execution_attempt_id", "sequence", name="uq_execution_attempt_events_sequence"
        ),
        CheckConstraint("sequence >= 0", name="ck_execution_attempt_events_sequence"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    execution_attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_attempts.id", ondelete="RESTRICT")
    )
    sequence: Mapped[int] = mapped_column(Integer)
    previous_state: Mapped[str | None] = mapped_column(String(24))
    new_state: Mapped[str] = mapped_column(String(24))
    reason_code: Mapped[str] = mapped_column(String(64))
    safe_correlation: Mapped[str | None] = mapped_column(String(120))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProviderReceipt(Base):
    """Bounded proof that HubSpot accepted and identified a Task."""

    __tablename__ = "provider_receipts"
    __table_args__ = (
        UniqueConstraint("execution_attempt_id", name="uq_provider_receipts_attempt"),
        UniqueConstraint(
            "portal_scope_hash", "provider_object_id", name="uq_provider_receipts_task"
        ),
        CheckConstraint(
            "provider_type = 'HUBSPOT' AND provider_object_type = 'TASK'",
            name="ck_provider_receipts_kind",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    execution_plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_plans.id", ondelete="RESTRICT")
    )
    execution_attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_attempts.id", ondelete="RESTRICT")
    )
    provider_type: Mapped[str] = mapped_column(String(20))
    portal_scope_hash: Mapped[str] = mapped_column(String(64))
    provider_object_type: Mapped[str] = mapped_column(String(20))
    provider_object_id: Mapped[str] = mapped_column(String(30))
    request_correlation: Mapped[str | None] = mapped_column(String(120))
    http_result_class: Mapped[str] = mapped_column(String(24))
    provider_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    adapter_version: Mapped[str] = mapped_column(String(32))
    api_version: Mapped[str] = mapped_column(String(16))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_hash: Mapped[str] = mapped_column(String(64))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExecutionReconciliation(Base):
    """One bounded read-back conclusion, including negative and uncertain results."""

    __tablename__ = "execution_reconciliations"
    __table_args__ = (
        CheckConstraint(
            "result IN ('CONFIRMED','NOT_FOUND','MISMATCH','UNKNOWN')",
            name="ck_execution_reconciliations_result",
        ),
        CheckConstraint(
            "read_count BETWEEN 0 AND 20", name="ck_execution_reconciliations_read_count"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    execution_attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_attempts.id", ondelete="RESTRICT")
    )
    provider_receipt_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("provider_receipts.id", ondelete="RESTRICT")
    )
    result: Mapped[str] = mapped_column(String(16))
    reason_code: Mapped[str] = mapped_column(String(64))
    provider_task_id: Mapped[str | None] = mapped_column(String(30))
    read_count: Mapped[int] = mapped_column(Integer)
    observed_hash: Mapped[str | None] = mapped_column(String(64))
    reconciled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OperationalOutcome(Base):
    """Verified external Task creation only; never a seller/commercial outcome."""

    __tablename__ = "operational_outcomes"
    __table_args__ = (
        UniqueConstraint("execution_plan_id", name="uq_operational_outcomes_plan"),
        UniqueConstraint("execution_attempt_id", name="uq_operational_outcomes_attempt"),
        CheckConstraint(
            "reason_code = 'CRM_TASK_CONFIRMED_CREATED'", name="ck_operational_outcomes_reason"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    execution_plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_plans.id", ondelete="RESTRICT")
    )
    execution_attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_attempts.id", ondelete="RESTRICT")
    )
    execution_reconciliation_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_reconciliations.id", ondelete="RESTRICT")
    )
    reason_code: Mapped[str] = mapped_column(String(64))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
