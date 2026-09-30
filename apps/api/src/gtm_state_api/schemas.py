"""Typed public API contracts for health and canonical GTM read models."""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gtm_state_api.types import (
    EvidenceAssertion,
    EvidenceClassification,
    EvidenceFreshness,
    SignalCategory,
    SignalDefinitionStatus,
    SignalEvaluationResult,
    SignalReasonCode,
    SignalResolvedFreshness,
    SignalResolvedStatus,
    StrategyStatus,
    StrategyTopic,
)


class LivenessResponse(BaseModel):
    """Process-level liveness without infrastructure details."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = "ok"
    service: Literal["gtm-state-api"] = "gtm-state-api"
    version: str


class ReadinessResponse(BaseModel):
    """Dependency readiness without leaking database details."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "not_ready"]


class WorkspaceResponse(BaseModel):
    """Public workspace boundary for the synthetic demo."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    workspace_id: UUID
    slug: str
    name: str
    demo_mode: bool
    demo_as_of: datetime | None


class EvidenceResponse(BaseModel):
    """Provenance-bearing evidence, with epistemic confidence only where applicable."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    strategy_version_id: UUID | None
    account_id: UUID | None
    strategy_topic: StrategyTopic | None
    classification: EvidenceClassification
    source_provider: str
    source_reference: str
    source_uri: str | None
    observed_at: datetime
    ingested_at: datetime
    normalized_fact: str
    raw_payload_hash: str | None
    freshness: EvidenceFreshness
    confidence: Decimal | None
    fact_key: str | None = None
    fact_assertion: EvidenceAssertion | None = None


class EvidenceValidationInput(BaseModel):
    """Validation boundary reused by the seed and failure-path tests.

    Confidence reflects epistemic interpretation or hypothesis confidence. It is not an
    extraction or model-parsing confidence, which belongs to a later evidence-quality layer.
    """

    model_config = ConfigDict(extra="forbid")

    strategy_version_id: UUID | None = None
    account_id: UUID | None = None
    strategy_topic: StrategyTopic | None = None
    classification: EvidenceClassification
    source_provider: str = Field(min_length=1, max_length=120)
    source_reference: str = Field(min_length=1)
    source_uri: str | None = None
    observed_at: datetime
    ingested_at: datetime
    normalized_fact: str = Field(min_length=1)
    raw_payload_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    freshness: EvidenceFreshness
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    fact_key: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_.]*$")
    fact_assertion: EvidenceAssertion | None = None

    @model_validator(mode="after")
    def validate_m1a_evidence_shape(self) -> Self:
        """Require exactly one target and confidence rules that match epistemic status."""

        has_strategy_target = self.strategy_version_id is not None
        has_account_target = self.account_id is not None
        if has_strategy_target == has_account_target:
            raise ValueError("evidence must target exactly one strategy version or account")
        if has_strategy_target != (self.strategy_topic is not None):
            raise ValueError("strategy topic is required only for strategy evidence")
        if self.classification is EvidenceClassification.FACT and self.confidence is not None:
            raise ValueError("FACT evidence must not include epistemic confidence")
        if (self.fact_key is None) != (self.fact_assertion is None):
            raise ValueError("fact key and assertion must be provided together")
        if has_strategy_target and self.fact_key is not None:
            raise ValueError("strategy evidence cannot be a normalized account fact")
        return self


class StrategyResponse(BaseModel):
    """The active strategy plus synthetic hypothesis evidence."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    workspace_id: UUID
    semantic_version: str
    status: StrategyStatus
    name: str
    summary: str
    synthetic_disclaimer: str
    created_at: datetime
    activated_at: datetime | None
    claims: list[EvidenceResponse]


class ActiveStrategyResponse(BaseModel):
    """Envelope preserving workspace demo-time semantics."""

    model_config = ConfigDict(extra="forbid")

    workspace: WorkspaceResponse
    strategy: StrategyResponse


class AccountResponse(BaseModel):
    """Canonical account identity, explicitly free of derived state."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    workspace_id: UUID
    slug: str
    canonical_name: str
    domain: str
    segment: str
    is_synthetic: bool
    created_at: datetime
    updated_at: datetime


class AccountListResponse(BaseModel):
    """Paginated workspace-scoped account read model."""

    model_config = ConfigDict(extra="forbid")

    workspace: WorkspaceResponse
    items: list[AccountResponse]
    limit: int
    offset: int


class AccountDetailResponse(BaseModel):
    """Account detail envelope for the read-only product view."""

    model_config = ConfigDict(extra="forbid")

    workspace: WorkspaceResponse
    account: AccountResponse


class EvidenceListResponse(BaseModel):
    """Evidence list for one supported M1A target."""

    model_config = ConfigDict(extra="forbid")

    items: list[EvidenceResponse]


class SignalDefinitionResponse(BaseModel):
    """Versioned deterministic signal definition."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    signal_definition_id: UUID
    workspace_id: UUID
    strategy_version_id: UUID
    stable_key: str
    display_name: str
    description: str
    category: SignalCategory
    input_fact_key: str
    evaluator_key: str
    freshness_window_days: int
    rule_version: str
    status: SignalDefinitionStatus
    created_at: datetime


class SignalEvaluationResponse(BaseModel):
    """One reproducible deterministic evaluation at a semantic time."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    evaluation_id: UUID
    workspace_id: UUID
    account_id: UUID
    signal_definition_id: UUID
    strategy_version_id: UUID
    signal_id: UUID | None
    evaluation_as_of: datetime
    evaluated_at: datetime
    input_hash: str
    result: SignalEvaluationResult
    reason_code: SignalReasonCode
    rule_version: str
    created_at: datetime


class CanonicalSignalResponse(BaseModel):
    """Stable commercial-event identity independent of evaluation time."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    signal_id: UUID
    workspace_id: UUID
    account_id: UUID
    signal_definition_id: UUID
    strategy_version_id: UUID
    event_fingerprint: str
    observed_at: datetime
    first_detected_at: datetime
    origin_evaluation_id: UUID
    created_at: datetime


class SignalReadModel(BaseModel):
    """Canonical signal with status resolved from its latest evaluation."""

    model_config = ConfigDict(extra="forbid")

    signal: CanonicalSignalResponse
    definition: SignalDefinitionResponse
    current_evaluation: SignalEvaluationResponse
    current_status: SignalResolvedStatus
    current_freshness: SignalResolvedFreshness
    evidence: list[EvidenceResponse]


class SignalEvaluationTraceResponse(BaseModel):
    """Evaluation result and its complete relational evidence trace."""

    model_config = ConfigDict(extra="forbid")

    evaluation: SignalEvaluationResponse
    definition: SignalDefinitionResponse
    evidence: list[EvidenceResponse]


class SignalDefinitionListResponse(BaseModel):
    """Definitions governed by the active workspace strategy."""

    model_config = ConfigDict(extra="forbid")

    workspace: WorkspaceResponse
    strategy_version_id: UUID
    items: list[SignalDefinitionResponse]


class AccountSignalListResponse(BaseModel):
    """Canonical events for one account at the workspace snapshot."""

    model_config = ConfigDict(extra="forbid")

    workspace: WorkspaceResponse
    account_id: UUID
    items: list[SignalReadModel]


class AccountSignalEvaluationListResponse(BaseModel):
    """All preserved deterministic results for one account."""

    model_config = ConfigDict(extra="forbid")

    workspace: WorkspaceResponse
    account_id: UUID
    items: list[SignalEvaluationTraceResponse]
