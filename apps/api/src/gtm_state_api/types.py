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
