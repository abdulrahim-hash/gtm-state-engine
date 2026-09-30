"""Unit tests for M1B.1 deterministic evaluator semantics."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from gtm_state_api.models import Evidence, SignalDefinition
from gtm_state_api.signal_engine import (
    EVALUATOR_REGISTRY,
    latest_assertion_with_freshness,
)
from gtm_state_api.types import (
    EvidenceAssertion,
    EvidenceClassification,
    EvidenceFreshness,
    SignalCategory,
    SignalDefinitionStatus,
    SignalEvaluationResult,
    SignalReasonCode,
)

AS_OF = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


def _definition(window: int = 90) -> SignalDefinition:
    return SignalDefinition(
        signal_definition_id=uuid4(),
        workspace_id=uuid4(),
        strategy_version_id=uuid4(),
        stable_key="new_revenue_leader",
        display_name="New revenue leader",
        description="Synthetic test definition.",
        category=SignalCategory.LEADERSHIP,
        input_fact_key="commercial_event.new_revenue_leader",
        evaluator_key="latest_assertion_with_freshness",
        freshness_window_days=window,
        rule_version="1.0.0",
        status=SignalDefinitionStatus.ENABLED,
        created_at=AS_OF,
    )


def _evidence(
    assertion: EvidenceAssertion,
    observed_at: datetime,
) -> Evidence:
    return Evidence(
        id=uuid4(),
        strategy_version_id=None,
        account_id=uuid4(),
        strategy_topic=None,
        classification=EvidenceClassification.FACT,
        source_provider="synthetic_test",
        source_reference=f"synthetic://test/{uuid4()}",
        source_uri=None,
        observed_at=observed_at,
        ingested_at=AS_OF,
        normalized_fact="Synthetic evaluator input.",
        raw_payload_hash=None,
        freshness=EvidenceFreshness.CURRENT,
        confidence=None,
        fact_key="commercial_event.new_revenue_leader",
        fact_assertion=assertion,
    )


def test_registry_uses_explicit_evaluator_key_and_rule_version() -> None:
    assert (
        EVALUATOR_REGISTRY[("latest_assertion_with_freshness", "1.0.0")]
        is latest_assertion_with_freshness
    )


def test_present_event_at_inclusive_boundary_is_detected() -> None:
    evidence = _evidence(EvidenceAssertion.PRESENT, AS_OF - timedelta(days=90))

    decision = latest_assertion_with_freshness(_definition(), [evidence], AS_OF)

    assert decision.result is SignalEvaluationResult.DETECTED
    assert decision.reason_code is SignalReasonCode.QUALIFYING_EVENT_WITHIN_WINDOW
    assert decision.event_evidence == (evidence,)


def test_present_event_outside_window_is_stale() -> None:
    evidence = _evidence(EvidenceAssertion.PRESENT, AS_OF - timedelta(days=91))

    decision = latest_assertion_with_freshness(_definition(), [evidence], AS_OF)

    assert decision.result is SignalEvaluationResult.STALE
    assert decision.reason_code is SignalReasonCode.QUALIFYING_EVENT_OUTSIDE_WINDOW


def test_explicit_absence_is_no_match() -> None:
    evidence = _evidence(EvidenceAssertion.ABSENT, AS_OF - timedelta(days=1))

    decision = latest_assertion_with_freshness(_definition(), [evidence], AS_OF)

    assert decision.result is SignalEvaluationResult.NO_MATCH
    assert decision.reason_code is SignalReasonCode.SUFFICIENT_EVIDENCE_NO_EVENT
    assert not decision.event_evidence


def test_missing_and_ambiguous_evidence_are_distinct_inconclusive_results() -> None:
    missing = latest_assertion_with_freshness(_definition(), [], AS_OF)
    ambiguous = latest_assertion_with_freshness(
        _definition(),
        [_evidence(EvidenceAssertion.INCONCLUSIVE, AS_OF)],
        AS_OF,
    )

    assert missing.result is SignalEvaluationResult.INCONCLUSIVE
    assert missing.reason_code is SignalReasonCode.REQUIRED_EVIDENCE_MISSING
    assert ambiguous.result is SignalEvaluationResult.INCONCLUSIVE
    assert ambiguous.reason_code is SignalReasonCode.EVIDENCE_AMBIGUOUS


def test_conflicting_latest_assertions_are_inconclusive() -> None:
    decision = latest_assertion_with_freshness(
        _definition(),
        [
            _evidence(EvidenceAssertion.PRESENT, AS_OF),
            _evidence(EvidenceAssertion.ABSENT, AS_OF),
        ],
        AS_OF,
    )

    assert decision.result is SignalEvaluationResult.INCONCLUSIVE
    assert decision.reason_code is SignalReasonCode.EVIDENCE_CONTRADICTORY
