"""Shared controlled vocabularies for canonical GTM records."""

from enum import StrEnum


class StrategyStatus(StrEnum):
    """Lifecycle statuses for a versioned strategy."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class EvidenceClassification(StrEnum):
    """Epistemic status of an evidence record."""

    FACT = "FACT"
    INFERENCE = "INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"


class EvidenceFreshness(StrEnum):
    """Fixture-declared freshness relative to the workspace demo snapshot."""

    CURRENT = "CURRENT"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class EvidenceAssertion(StrEnum):
    """Machine-readable assertion carried by normalized account evidence."""

    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    INCONCLUSIVE = "INCONCLUSIVE"


class IngestionRowOutcome(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNRESOLVED = "UNRESOLVED"
    DUPLICATE = "DUPLICATE"


class NormalizationOutcome(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNRESOLVED = "UNRESOLVED"
    CONFLICT = "CONFLICT"


class IngestionReason(StrEnum):
    INVALID_ROW = "INVALID_ROW"
    INVALID_DATE = "INVALID_DATE"
    INVALID_ASSERTION = "INVALID_ASSERTION"
    INVALID_CITATION = "INVALID_CITATION"
    FIELD_TOO_LARGE = "FIELD_TOO_LARGE"
    UNSUPPORTED_FACT = "UNSUPPORTED_FACT"
    EVENT_TIME_REQUIRED = "EVENT_TIME_REQUIRED"
    MISSING_IDENTITY = "MISSING_IDENTITY"
    AMBIGUOUS_IDENTITY = "AMBIGUOUS_IDENTITY"
    SOURCE_ID_CONFLICT = "SOURCE_ID_CONFLICT"
    SOURCE_RECORD_CONFLICT = "SOURCE_RECORD_CONFLICT"
    DUPLICATE_OBSERVATION = "DUPLICATE_OBSERVATION"


class EvidenceSupersessionReason(StrEnum):
    MAPPER_VERSION_PROMOTION = "MAPPER_VERSION_PROMOTION"
    IDENTITY_RULE_PROMOTION = "IDENTITY_RULE_PROMOTION"


class SignalCategory(StrEnum):
    """Commercial-event families supported by signal definitions."""

    LEADERSHIP = "LEADERSHIP"
    HIRING = "HIRING"
    FUNDING = "FUNDING"
    EXPANSION = "EXPANSION"
    TECHNOLOGY = "TECHNOLOGY"
    ENGAGEMENT = "ENGAGEMENT"


class SignalDefinitionStatus(StrEnum):
    """Lifecycle status for an immutable signal-definition version."""

    ENABLED = "ENABLED"
    DISABLED = "DISABLED"


class SignalEvaluationResult(StrEnum):
    """Exhaustive deterministic evaluation outcomes."""

    DETECTED = "DETECTED"
    NO_MATCH = "NO_MATCH"
    INCONCLUSIVE = "INCONCLUSIVE"
    STALE = "STALE"


class SignalReasonCode(StrEnum):
    """Stable explanations emitted by deterministic evaluators."""

    QUALIFYING_EVENT_WITHIN_WINDOW = "QUALIFYING_EVENT_WITHIN_WINDOW"
    QUALIFYING_EVENT_OUTSIDE_WINDOW = "QUALIFYING_EVENT_OUTSIDE_WINDOW"
    SUFFICIENT_EVIDENCE_NO_EVENT = "SUFFICIENT_EVIDENCE_NO_EVENT"
    REQUIRED_EVIDENCE_MISSING = "REQUIRED_EVIDENCE_MISSING"
    EVIDENCE_AMBIGUOUS = "EVIDENCE_AMBIGUOUS"
    EVIDENCE_CONTRADICTORY = "EVIDENCE_CONTRADICTORY"


class SignalResolvedStatus(StrEnum):
    """Current presentation status derived from the latest linked evaluation."""

    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"


class SignalResolvedFreshness(StrEnum):
    """Current presentation freshness derived rather than stored on a signal."""

    CURRENT = "CURRENT"
    STALE = "STALE"


class AccountFitContext(StrEnum):
    """Descriptive fit relative to one explicit strategy hypothesis."""

    MATCH = "MATCH"
    PARTIAL = "PARTIAL"
    MISMATCH = "MISMATCH"
    UNKNOWN = "UNKNOWN"
    INCONCLUSIVE = "INCONCLUSIVE"


class AccountTimingState(StrEnum):
    """Current commercial-change state derived from signal evaluations."""

    ACTIVE = "ACTIVE"
    STALE = "STALE"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"
    INCONCLUSIVE = "INCONCLUSIVE"


class AccountRelationshipState(StrEnum):
    """Known existing-relationship context without policy implications."""

    EXISTING_RELATIONSHIP = "EXISTING_RELATIONSHIP"
    NO_EXISTING_RELATIONSHIP = "NO_EXISTING_RELATIONSHIP"
    UNKNOWN = "UNKNOWN"
    INCONCLUSIVE = "INCONCLUSIVE"


class AccountEvidenceSufficiency(StrEnum):
    """Categorical state-input coverage, never a probability or score."""

    SUFFICIENT = "SUFFICIENT"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"
    CONTRADICTORY = "CONTRADICTORY"


class AccountStateFacet(StrEnum):
    """Facet names used by normalized snapshot explanations."""

    FIT_CONTEXT = "FIT_CONTEXT"
    TIMING_STATE = "TIMING_STATE"
    RELATIONSHIP_STATE = "RELATIONSHIP_STATE"
    EVIDENCE_SUFFICIENCY = "EVIDENCE_SUFFICIENCY"


class FitCriterionResult(StrEnum):
    """One criterion's non-numeric result inside a fit evaluation."""

    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    UNKNOWN = "UNKNOWN"
    INCONCLUSIVE = "INCONCLUSIVE"


class AccountStateReasonCode(StrEnum):
    """Stable explanations emitted by deterministic account-state evaluators."""

    ALL_REQUIRED_FIT_CRITERIA_MATCH = "ALL_REQUIRED_FIT_CRITERIA_MATCH"
    FIT_CRITERION_MATCH = "FIT_CRITERION_MATCH"
    SOME_REQUIRED_FIT_CRITERIA_MATCH = "SOME_REQUIRED_FIT_CRITERIA_MATCH"
    REQUIRED_FIT_CRITERION_MISMATCH = "REQUIRED_FIT_CRITERION_MISMATCH"
    FIT_EVIDENCE_MISSING = "FIT_EVIDENCE_MISSING"
    FIT_EVIDENCE_NOT_CURRENT = "FIT_EVIDENCE_NOT_CURRENT"
    FIT_EVIDENCE_AMBIGUOUS = "FIT_EVIDENCE_AMBIGUOUS"
    FIT_EVIDENCE_CONTRADICTORY = "FIT_EVIDENCE_CONTRADICTORY"
    CURRENT_SIGNAL_DETECTED = "CURRENT_SIGNAL_DETECTED"
    STALE_SIGNAL_PRESENT = "STALE_SIGNAL_PRESENT"
    ALL_SIGNAL_EVALUATIONS_NO_MATCH = "ALL_SIGNAL_EVALUATIONS_NO_MATCH"
    NO_ENABLED_SIGNAL_DEFINITIONS = "NO_ENABLED_SIGNAL_DEFINITIONS"
    SIGNAL_EVALUATION_MISSING = "SIGNAL_EVALUATION_MISSING"
    SIGNAL_EVIDENCE_MISSING = "SIGNAL_EVIDENCE_MISSING"
    SIGNAL_EVIDENCE_AMBIGUOUS = "SIGNAL_EVIDENCE_AMBIGUOUS"
    SIGNAL_EVIDENCE_CONTRADICTORY = "SIGNAL_EVIDENCE_CONTRADICTORY"
    EXISTING_RELATIONSHIP_PRESENT = "EXISTING_RELATIONSHIP_PRESENT"
    EXISTING_RELATIONSHIP_ABSENT = "EXISTING_RELATIONSHIP_ABSENT"
    RELATIONSHIP_EVIDENCE_MISSING = "RELATIONSHIP_EVIDENCE_MISSING"
    RELATIONSHIP_EVIDENCE_NOT_CURRENT = "RELATIONSHIP_EVIDENCE_NOT_CURRENT"
    RELATIONSHIP_EVIDENCE_AMBIGUOUS = "RELATIONSHIP_EVIDENCE_AMBIGUOUS"
    RELATIONSHIP_EVIDENCE_CONTRADICTORY = "RELATIONSHIP_EVIDENCE_CONTRADICTORY"
    ALL_REQUIRED_STATE_INPUTS_SUPPORTED = "ALL_REQUIRED_STATE_INPUTS_SUPPORTED"
    FIT_COVERAGE_INCOMPLETE = "FIT_COVERAGE_INCOMPLETE"
    TIMING_COVERAGE_INCOMPLETE = "TIMING_COVERAGE_INCOMPLETE"
    RELATIONSHIP_COVERAGE_INCOMPLETE = "RELATIONSHIP_COVERAGE_INCOMPLETE"
    CONTRADICTORY_STATE_INPUTS = "CONTRADICTORY_STATE_INPUTS"


class EvaluationDefinitionStatus(StrEnum):
    """Lifecycle status for versioned Decision and Policy definitions."""

    ENABLED = "ENABLED"
    DISABLED = "DISABLED"


class DecisionResult(StrEnum):
    """Deterministic response posture derived from one immutable state snapshot."""

    ENGAGE = "ENGAGE"
    HOLD = "HOLD"
    NO_ACTION = "NO_ACTION"
    ABSTAIN = "ABSTAIN"


class DecisionReasonCode(StrEnum):
    """Stable explanations emitted by the deterministic Decision evaluator."""

    FIT_MATCH_SUPPORTS_ENGAGEMENT = "FIT_MATCH_SUPPORTS_ENGAGEMENT"
    ACTIVE_TIMING_SUPPORTS_ENGAGEMENT = "ACTIVE_TIMING_SUPPORTS_ENGAGEMENT"
    FIT_MISMATCH_NO_PROSPECTING_BASIS = "FIT_MISMATCH_NO_PROSPECTING_BASIS"
    FIT_MATCH_BUT_NO_CURRENT_TIMING = "FIT_MATCH_BUT_NO_CURRENT_TIMING"
    FIT_MATCH_BUT_TIMING_STALE = "FIT_MATCH_BUT_TIMING_STALE"
    FIT_NOT_DETERMINATE = "FIT_NOT_DETERMINATE"
    TIMING_NOT_DETERMINATE = "TIMING_NOT_DETERMINATE"
    STATE_EVIDENCE_INSUFFICIENT = "STATE_EVIDENCE_INSUFFICIENT"
    STATE_EVIDENCE_CONTRADICTORY = "STATE_EVIDENCE_CONTRADICTORY"


class PolicyTarget(StrEnum):
    """Bounded subject evaluated by one Policy definition."""

    PROSPECTING_ACTIVATION = "PROSPECTING_ACTIVATION"


class PolicyResult(StrEnum):
    """Deterministic gate applied independently of Decision desirability."""

    ALLOW = "ALLOW"
    REQUIRE_REVIEW = "REQUIRE_REVIEW"
    BLOCK = "BLOCK"


class PolicyReasonCode(StrEnum):
    """Stable constraints emitted by the deterministic Policy evaluator."""

    DECISION_DOES_NOT_SUPPORT_ACTIVATION = "DECISION_DOES_NOT_SUPPORT_ACTIVATION"
    FIT_STATE_BLOCKS_ACTIVATION = "FIT_STATE_BLOCKS_ACTIVATION"
    TIMING_STATE_BLOCKS_ACTIVATION = "TIMING_STATE_BLOCKS_ACTIVATION"
    EVIDENCE_INSUFFICIENT_BLOCKS_ACTIVATION = "EVIDENCE_INSUFFICIENT_BLOCKS_ACTIVATION"
    EVIDENCE_CONTRADICTORY_BLOCKS_ACTIVATION = "EVIDENCE_CONTRADICTORY_BLOCKS_ACTIVATION"
    DECISION_STATE_MISMATCH = "DECISION_STATE_MISMATCH"
    EXISTING_RELATIONSHIP_REQUIRES_CONTROLLED_HANDLING = (
        "EXISTING_RELATIONSHIP_REQUIRES_CONTROLLED_HANDLING"
    )
    RELATIONSHIP_UNKNOWN_REQUIRES_REVIEW = "RELATIONSHIP_UNKNOWN_REQUIRES_REVIEW"
    RELATIONSHIP_INCONCLUSIVE_REQUIRES_REVIEW = "RELATIONSHIP_INCONCLUSIVE_REQUIRES_REVIEW"
    PARTIAL_EVIDENCE_REQUIRES_REVIEW = "PARTIAL_EVIDENCE_REQUIRES_REVIEW"
    EXPLICIT_NO_EXISTING_RELATIONSHIP = "EXPLICIT_NO_EXISTING_RELATIONSHIP"
    ALL_POLICY_CONSTRAINTS_SATISFIED = "ALL_POLICY_CONSTRAINTS_SATISFIED"


class ActionType(StrEnum):
    """Vendor-neutral GTM operational intents supported by M1D."""

    REQUEST_RESEARCH = "REQUEST_RESEARCH"
    CREATE_SELLER_TASK = "CREATE_SELLER_TASK"


class ActionLifecycle(StrEnum):
    """Read-only governance projection; never stored as mutable Action state."""

    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    READY_FOR_DRY_RUN = "READY_FOR_DRY_RUN"
    REJECTED = "REJECTED"


class ActionCurrentProjection(StrEnum):
    """Current account-level result, including non-Action abstentions."""

    ACTION_PROPOSED = "ACTION_PROPOSED"
    BLOCKED_BY_POLICY = "BLOCKED_BY_POLICY"
    NO_SUPPORTED_ACTION = "NO_SUPPORTED_ACTION"


class ResearchTopic(StrEnum):
    """Bounded subjects for a canonical research request."""

    RELATIONSHIP_CONTEXT = "RELATIONSHIP_CONTEXT"
    EVIDENCE_COVERAGE = "EVIDENCE_COVERAGE"


class ResearchRequestCode(StrEnum):
    """Non-executable research instructions."""

    VERIFY_EXISTING_RELATIONSHIP = "VERIFY_EXISTING_RELATIONSHIP"
    RESOLVE_EVIDENCE_GAPS = "RESOLVE_EVIDENCE_GAPS"


class SellerTaskKind(StrEnum):
    """Bounded seller-task intents without provider or assignment semantics."""

    RELATIONSHIP_COORDINATION = "RELATIONSHIP_COORDINATION"
    ENGAGEMENT_ASSESSMENT = "ENGAGEMENT_ASSESSMENT"


class SellerTaskObjectiveCode(StrEnum):
    """Bounded objectives for a proposed seller task."""

    ASSESS_CONTROLLED_ENGAGEMENT_PATH = "ASSESS_CONTROLLED_ENGAGEMENT_PATH"
    ASSESS_POLICY_ALLOWED_ENGAGEMENT = "ASSESS_POLICY_ALLOWED_ENGAGEMENT"


class ActionReviewResolution(StrEnum):
    """One terminal human resolution for a review-required Action."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ActionReviewReasonCode(StrEnum):
    """Bounded review explanations; M1D stores no free-form review text."""

    APPROVED_AS_PROPOSED = "APPROVED_AS_PROPOSED"
    REJECTED_INSUFFICIENT_CONTEXT = "REJECTED_INSUFFICIENT_CONTEXT"
    REJECTED_ACTION_NOT_APPROPRIATE = "REJECTED_ACTION_NOT_APPROPRIATE"


class ActionActorKind(StrEnum):
    """Honest identity assurance for unauthenticated demo events."""

    UNVERIFIED_DEMO_HUMAN = "UNVERIFIED_DEMO_HUMAN"
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"


class ActionAttemptMode(StrEnum):
    """M1D supports local validation only."""

    DRY_RUN = "DRY_RUN"


class ActionOutcomeResult(StrEnum):
    """Operational result of local deterministic validation."""

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ActionOutcomeReasonCode(StrEnum):
    """Strictly operational M1D Outcome reasons."""

    CANONICAL_ACTION_VALIDATED = "CANONICAL_ACTION_VALIDATED"
    CANONICAL_ACTION_INVALID = "CANONICAL_ACTION_INVALID"


class StrategyTopic(StrEnum):
    """Required synthetic strategy coverage areas."""

    MARKET = "MARKET"
    SEGMENTATION = "SEGMENTATION"
    ICP = "ICP"
    BUYER_HYPOTHESES = "BUYER_HYPOTHESES"
    PROBLEM_HYPOTHESIS = "PROBLEM_HYPOTHESIS"
    VALUE_PROPOSITION_HYPOTHESIS = "VALUE_PROPOSITION_HYPOTHESIS"
    OFFER_HYPOTHESIS = "OFFER_HYPOTHESIS"
    PRICING_HYPOTHESIS = "PRICING_HYPOTHESIS"
    MESSAGING_FRAMEWORK = "MESSAGING_FRAMEWORK"
    CHANNELS = "CHANNELS"
    GTM_MOTION = "GTM_MOTION"
    EXPERIMENT_ASSUMPTIONS = "EXPERIMENT_ASSUMPTIONS"
