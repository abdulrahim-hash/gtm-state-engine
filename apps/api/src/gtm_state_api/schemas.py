"""Typed public API contracts for health and canonical GTM read models."""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gtm_state_api.types import (
    AccountEvidenceSufficiency,
    AccountFitContext,
    AccountRelationshipState,
    AccountStateFacet,
    AccountStateReasonCode,
    AccountTimingState,
    ActionActorKind,
    ActionAttemptMode,
    ActionCurrentProjection,
    ActionLifecycle,
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
    FitCriterionResult,
    PolicyReasonCode,
    PolicyResult,
    PolicyTarget,
    ResearchRequestCode,
    ResearchTopic,
    SellerTaskKind,
    SellerTaskObjectiveCode,
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
    segment: str | None
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


class StrategyFitCriterionResponse(BaseModel):
    """Executable fit criterion tied to one strategy hypothesis."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    fit_criterion_id: UUID
    workspace_id: UUID
    strategy_version_id: UUID
    stable_key: str
    display_name: str
    description: str
    input_fact_key: str
    expected_assertion: EvidenceAssertion
    source_strategy_evidence_id: UUID
    created_at: datetime


class AccountStateSnapshotResponse(BaseModel):
    """Immutable descriptive account-state snapshot."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    state_snapshot_id: UUID
    workspace_id: UUID
    account_id: UUID
    strategy_version_id: UUID
    state_as_of: datetime
    computed_at: datetime
    input_hash: str
    state_engine_version: str
    fit_context: AccountFitContext
    timing_state: AccountTimingState
    relationship_state: AccountRelationshipState
    evidence_sufficiency: AccountEvidenceSufficiency
    created_at: datetime


class AccountStateReasonResponse(BaseModel):
    """One ordered, facet-scoped explanation."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    facet: AccountStateFacet
    position: int
    reason_code: AccountStateReasonCode


class StateEvaluatorReferenceResponse(BaseModel):
    """Code-owned evaluator identity."""

    model_config = ConfigDict(extra="forbid")

    evaluator_key: str
    version: str


class StateEvaluatorManifestResponse(BaseModel):
    """Exact facet evaluator manifest for a state-engine version."""

    model_config = ConfigDict(extra="forbid")

    fit: StateEvaluatorReferenceResponse
    timing: StateEvaluatorReferenceResponse
    relationship: StateEvaluatorReferenceResponse
    evidence_sufficiency: StateEvaluatorReferenceResponse


class FitCriterionTraceResponse(BaseModel):
    """Frozen criterion result and its strategy/account provenance."""

    model_config = ConfigDict(extra="forbid")

    criterion: StrategyFitCriterionResponse
    fit_criterion_id: UUID
    criterion_stable_key: str
    input_fact_key: str
    source_strategy_evidence_id: UUID
    criterion_result: FitCriterionResult
    expected_assertion: EvidenceAssertion
    observed_assertion: EvidenceAssertion | None
    source_strategy_evidence: EvidenceResponse
    account_evidence: list[EvidenceResponse]


class AccountStateDetailResponse(BaseModel):
    """One snapshot with normalized explanations and full input traces."""

    model_config = ConfigDict(extra="forbid")

    workspace: WorkspaceResponse
    snapshot: AccountStateSnapshotResponse
    evaluator_manifest: StateEvaluatorManifestResponse
    reasons: list[AccountStateReasonResponse]
    fit_criteria: list[FitCriterionTraceResponse]
    relationship_evidence: list[EvidenceResponse]
    signal_evaluations: list[SignalEvaluationTraceResponse]


class AccountStateHistoryResponse(BaseModel):
    """Paginated immutable snapshots for one account."""

    model_config = ConfigDict(extra="forbid")

    workspace: WorkspaceResponse
    account_id: UUID
    items: list[AccountStateSnapshotResponse]
    limit: int
    offset: int


class DecisionDefinitionResponse(BaseModel):
    """Versioned selector for one code-owned deterministic Decision evaluator."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    decision_definition_id: UUID
    workspace_id: UUID
    strategy_version_id: UUID
    stable_key: str
    definition_version: str
    display_name: str
    description: str
    evaluator_key: str
    evaluator_version: str
    status: EvaluationDefinitionStatus
    created_at: datetime


class DecisionEvaluationResponse(BaseModel):
    """Immutable response posture for one exact account-state snapshot."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    decision_evaluation_id: UUID
    workspace_id: UUID
    account_id: UUID
    strategy_version_id: UUID
    state_snapshot_id: UUID
    decision_definition_id: UUID
    definition_version: str
    evaluated_at: datetime
    input_hash: str
    result: DecisionResult = Field(
        description=(
            "Deterministic response posture. ENGAGE means engagement merits consideration; "
            "it is not an execution command or external-action authorization."
        )
    )
    created_at: datetime


class DecisionEvaluationReasonResponse(BaseModel):
    """One stable ordered explanation for a Decision result."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    position: int
    reason_code: DecisionReasonCode


class PolicyDefinitionResponse(BaseModel):
    """Versioned selector for one code-owned deterministic Policy evaluator."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    policy_definition_id: UUID
    workspace_id: UUID
    strategy_version_id: UUID
    stable_key: str
    definition_version: str
    display_name: str
    description: str
    target: PolicyTarget
    evaluator_key: str
    evaluator_version: str
    status: EvaluationDefinitionStatus
    created_at: datetime


class PolicyEvaluationResponse(BaseModel):
    """Immutable gate for a Decision and the exact same account-state snapshot."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    policy_evaluation_id: UUID
    workspace_id: UUID
    account_id: UUID
    strategy_version_id: UUID
    state_snapshot_id: UUID
    decision_evaluation_id: UUID
    policy_definition_id: UUID
    definition_version: str
    evaluated_at: datetime
    input_hash: str
    result: PolicyResult = Field(
        description=("Gate for future planning only. ALLOW does not authorize an external action.")
    )
    created_at: datetime


class PolicyEvaluationReasonResponse(BaseModel):
    """One stable ordered constraint for a Policy result."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    position: int
    reason_code: PolicyReasonCode


class DecisionTraceResponse(BaseModel):
    """Decision evaluation with its exact version and ordered reasons."""

    model_config = ConfigDict(extra="forbid")

    definition: DecisionDefinitionResponse
    evaluation: DecisionEvaluationResponse
    reasons: list[DecisionEvaluationReasonResponse]


class PolicyTraceResponse(BaseModel):
    """Policy evaluation with its exact version and ordered reasons."""

    model_config = ConfigDict(extra="forbid")

    definition: PolicyDefinitionResponse
    evaluation: PolicyEvaluationResponse
    reasons: list[PolicyEvaluationReasonResponse]


class ProposedDispositionResponse(BaseModel):
    """Non-executing composition of separate immutable Decision and Policy results."""

    model_config = ConfigDict(extra="forbid")

    state_snapshot_id: UUID
    decision_evaluation_id: UUID
    policy_evaluation_id: UUID
    proposed_response: DecisionResult = Field(
        description=(
            "Proposed response posture. ENGAGE means engagement merits consideration only."
        )
    )
    proposed_response_label: str
    policy_result: PolicyResult
    lifecycle: Literal["PROPOSED_ONLY"] = "PROPOSED_ONLY"
    external_action_authorized: Literal[False] = False


class DecisionPolicyHistoryItemResponse(BaseModel):
    """One immutable Decision/Policy pair anchored to an exact state snapshot."""

    model_config = ConfigDict(extra="forbid")

    state_snapshot: AccountStateSnapshotResponse
    decision: DecisionTraceResponse
    policy: PolicyTraceResponse
    disposition: ProposedDispositionResponse


class DecisionPolicyDetailResponse(DecisionPolicyHistoryItemResponse):
    """Detailed current or historical M1C read model."""

    workspace: WorkspaceResponse


class AccountDecisionHistoryResponse(BaseModel):
    """Paginated immutable Decision and Policy history for one account."""

    model_config = ConfigDict(extra="forbid")

    workspace: WorkspaceResponse
    account_id: UUID
    items: list[DecisionPolicyHistoryItemResponse]
    limit: int
    offset: int


class RequestResearchPayload(BaseModel):
    """Strict provider-neutral payload for an account research request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    research_topic: ResearchTopic
    request_code: ResearchRequestCode


class CreateSellerTaskPayload(BaseModel):
    """Strict provider-neutral payload for a proposed seller task."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_kind: SellerTaskKind
    objective_code: SellerTaskObjectiveCode


ActionPayload = RequestResearchPayload | CreateSellerTaskPayload


class ActionResponse(BaseModel):
    """Immutable canonical Action proposal; never proof of external execution."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    action_id: UUID
    workspace_id: UUID
    account_id: UUID
    strategy_version_id: UUID
    policy_evaluation_id: UUID
    action_type: ActionType
    action_schema_version: str
    derivation_key: str
    derivation_version: str
    payload: ActionPayload
    semantic_input_hash: str
    proposed_at: datetime
    created_at: datetime
    external_execution_authorized: Literal[False] = False

    @model_validator(mode="after")
    def validate_payload_type(self) -> Self:
        if self.action_schema_version != "1.0.0":
            raise ValueError("unsupported Action schema version")
        if self.action_type is ActionType.REQUEST_RESEARCH and not isinstance(
            self.payload, RequestResearchPayload
        ):
            raise ValueError("REQUEST_RESEARCH payload shape does not match Action type")
        if self.action_type is ActionType.CREATE_SELLER_TASK and not isinstance(
            self.payload, CreateSellerTaskPayload
        ):
            raise ValueError("CREATE_SELLER_TASK payload shape does not match Action type")
        return self


class ActionReviewRequest(BaseModel):
    """Bounded unauthenticated-demo review command."""

    model_config = ConfigDict(extra="forbid")

    resolution: ActionReviewResolution
    reason_code: ActionReviewReasonCode

    @model_validator(mode="after")
    def validate_reason_for_resolution(self) -> Self:
        if (
            self.resolution is ActionReviewResolution.APPROVED
            and self.reason_code is not ActionReviewReasonCode.APPROVED_AS_PROPOSED
        ):
            raise ValueError("APPROVED requires APPROVED_AS_PROPOSED")
        if (
            self.resolution is ActionReviewResolution.REJECTED
            and self.reason_code is ActionReviewReasonCode.APPROVED_AS_PROPOSED
        ):
            raise ValueError("REJECTED requires a rejection reason")
        return self


class ActionReviewResponse(BaseModel):
    """One immutable terminal review with honest identity assurance."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    review_id: UUID
    action_id: UUID
    resolution: ActionReviewResolution
    reason_code: ActionReviewReasonCode
    reviewer_kind: ActionActorKind
    reviewer_ref: str
    reviewed_at: datetime
    created_at: datetime


class ActionAttemptResponse(BaseModel):
    """Immutable local dry-run validation attempt."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    action_attempt_id: UUID
    action_id: UUID
    review_id: UUID | None
    mode: ActionAttemptMode
    validator_key: str
    validator_version: str
    input_hash: str
    requested_by_kind: ActionActorKind
    requested_by_ref: str
    attempted_at: datetime
    created_at: datetime


class ActionOutcomeResponse(BaseModel):
    """Strictly operational result of local canonical validation."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    outcome_id: UUID
    action_id: UUID
    action_attempt_id: UUID
    result: ActionOutcomeResult
    reason_code: ActionOutcomeReasonCode
    outcome_schema_version: str
    result_hash: str
    external_side_effects: Literal[False]
    observed_at: datetime
    created_at: datetime


class ActionAttemptTraceResponse(BaseModel):
    """A dry-run attempt and its one operational Outcome."""

    model_config = ConfigDict(extra="forbid")

    attempt: ActionAttemptResponse
    outcome: ActionOutcomeResponse


class ActionDetailResponse(BaseModel):
    """Action proposal with projected governance and operational history."""

    model_config = ConfigDict(extra="forbid")

    action: ActionResponse
    lifecycle: ActionLifecycle
    review: ActionReviewResponse | None
    attempts: list[ActionAttemptTraceResponse]
    mutations_enabled: bool
    external_execution_authorized: Literal[False] = False


class CurrentActionProjectionResponse(BaseModel):
    """Current M1D result, including non-persisted BLOCK/abstention projections."""

    model_config = ConfigDict(extra="forbid")

    projection: ActionCurrentProjection
    policy_evaluation_id: UUID
    policy_result: PolicyResult
    policy_reason_codes: list[PolicyReasonCode]
    action: ActionDetailResponse | None
    external_execution_authorized: Literal[False] = False


class CurrentAccountActionResponse(BaseModel):
    """Current exact Decision/Policy disposition and its M1D projection."""

    model_config = ConfigDict(extra="forbid")

    workspace: WorkspaceResponse
    account_id: UUID
    upstream: DecisionPolicyDetailResponse
    current: CurrentActionProjectionResponse


class AccountActionHistoryResponse(BaseModel):
    """Persisted Action history only; non-Action projections never appear here."""

    model_config = ConfigDict(extra="forbid")

    workspace: WorkspaceResponse
    account_id: UUID
    items: list[ActionDetailResponse]
    limit: int
    offset: int


class ActionOutcomeListResponse(BaseModel):
    """Immutable operational Outcomes for one Action."""

    model_config = ConfigDict(extra="forbid")

    action_id: UUID
    items: list[ActionOutcomeResponse]


class ActionTraceResponse(BaseModel):
    """Composed end-to-end trace without stored provenance duplication."""

    model_config = ConfigDict(extra="forbid")

    strategy: StrategyResponse
    state: AccountStateDetailResponse
    upstream: DecisionPolicyDetailResponse
    action: ActionDetailResponse


class ActionReviewMutationResponse(BaseModel):
    """Result of an explicit local-demo review command."""

    model_config = ConfigDict(extra="forbid")

    review: ActionReviewResponse
    lifecycle: ActionLifecycle
    idempotent_replay: bool
    external_execution_authorized: Literal[False] = False


class ActionDryRunMutationResponse(BaseModel):
    """Result of local deterministic validation without external execution."""

    model_config = ConfigDict(extra="forbid")

    trace: ActionAttemptTraceResponse
    idempotent_replay: bool
    external_execution_authorized: Literal[False] = False
