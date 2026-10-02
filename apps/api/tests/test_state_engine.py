"""Unit tests for deterministic M1B.2 account-state semantics."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from gtm_state_api.models import (
    Evidence,
    SignalDefinition,
    SignalEvaluation,
    StrategyFitCriterion,
)
from gtm_state_api.state_engine import (
    STATE_ENGINE_REGISTRY,
    STATE_ENGINE_VERSION,
    Coverage,
    evaluate_evidence_sufficiency,
    evaluate_fit_context,
    evaluate_relationship_state,
    evaluate_timing_state,
    state_input_hash,
)
from gtm_state_api.types import (
    AccountEvidenceSufficiency,
    AccountFitContext,
    AccountRelationshipState,
    AccountTimingState,
    EvidenceAssertion,
    EvidenceClassification,
    EvidenceFreshness,
    SignalCategory,
    SignalDefinitionStatus,
    SignalEvaluationResult,
    SignalReasonCode,
)

AS_OF = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
WORKSPACE_ID = uuid4()
ACCOUNT_ID = uuid4()
STRATEGY_ID = uuid4()


def _evidence(
    fact_key: str,
    assertion: EvidenceAssertion,
    *,
    observed_at: datetime = AS_OF,
    freshness: EvidenceFreshness = EvidenceFreshness.CURRENT,
) -> Evidence:
    return Evidence(
        id=uuid4(),
        strategy_version_id=None,
        account_id=ACCOUNT_ID,
        strategy_topic=None,
        classification=EvidenceClassification.FACT,
        source_provider="synthetic_test",
        source_reference=f"synthetic://state-test/{uuid4()}",
        source_uri=None,
        observed_at=observed_at,
        ingested_at=AS_OF,
        normalized_fact="Synthetic state evaluator input.",
        raw_payload_hash=None,
        freshness=freshness,
        confidence=None,
        fact_key=fact_key,
        fact_assertion=assertion,
    )


def _strategy_evidence() -> Evidence:
    return Evidence(
        id=uuid4(),
        strategy_version_id=STRATEGY_ID,
        account_id=None,
        strategy_topic=None,
        classification=EvidenceClassification.HYPOTHESIS,
        source_provider="synthetic_test",
        source_reference=f"synthetic://strategy-test/{uuid4()}",
        source_uri=None,
        observed_at=AS_OF,
        ingested_at=AS_OF,
        normalized_fact="Synthetic strategy hypothesis.",
        raw_payload_hash=None,
        freshness=EvidenceFreshness.CURRENT,
        confidence=None,
        fact_key=None,
        fact_assertion=None,
    )


def _criterion(fact_key: str = "account_profile.target") -> StrategyFitCriterion:
    return StrategyFitCriterion(
        fit_criterion_id=uuid4(),
        workspace_id=WORKSPACE_ID,
        strategy_version_id=STRATEGY_ID,
        stable_key=fact_key.replace(".", "_"),
        display_name="Synthetic criterion",
        description="Synthetic test criterion.",
        input_fact_key=fact_key,
        expected_assertion=EvidenceAssertion.PRESENT,
        source_strategy_evidence_id=uuid4(),
        created_at=AS_OF,
    )


def _definition(stable_key: str = "event_one") -> SignalDefinition:
    return SignalDefinition(
        signal_definition_id=uuid4(),
        workspace_id=WORKSPACE_ID,
        strategy_version_id=STRATEGY_ID,
        stable_key=stable_key,
        display_name="Synthetic event",
        description="Synthetic test definition.",
        category=SignalCategory.LEADERSHIP,
        input_fact_key=f"commercial_event.{stable_key}",
        evaluator_key="latest_assertion_with_freshness",
        freshness_window_days=90,
        rule_version="1.0.0",
        status=SignalDefinitionStatus.ENABLED,
        created_at=AS_OF,
    )


def _evaluation(
    definition: SignalDefinition,
    result: SignalEvaluationResult,
    reason: SignalReasonCode,
) -> SignalEvaluation:
    return SignalEvaluation(
        evaluation_id=uuid4(),
        workspace_id=WORKSPACE_ID,
        account_id=ACCOUNT_ID,
        signal_definition_id=definition.signal_definition_id,
        strategy_version_id=STRATEGY_ID,
        signal_id=uuid4()
        if result in {SignalEvaluationResult.DETECTED, SignalEvaluationResult.STALE}
        else None,
        evaluation_as_of=AS_OF,
        evaluated_at=AS_OF + timedelta(minutes=1),
        input_hash="a" * 64,
        result=result,
        reason_code=reason,
        rule_version="1.0.0",
        created_at=AS_OF + timedelta(minutes=1),
    )


def test_registry_pins_every_facet_evaluator_version() -> None:
    manifest = STATE_ENGINE_REGISTRY[STATE_ENGINE_VERSION]

    assert manifest.fit == ("required_fit_criteria", "1.0.0")
    assert manifest.timing == ("signal_evaluation_rollup", "1.0.0")
    assert manifest.relationship == ("latest_relationship_assertion", "1.0.0")
    assert manifest.evidence_sufficiency == ("facet_coverage", "1.0.0")


def test_fit_match_mismatch_and_missing_are_explicit() -> None:
    criterion = _criterion()

    match = evaluate_fit_context(
        [criterion],
        [_evidence(criterion.input_fact_key, EvidenceAssertion.PRESENT)],
    )
    mismatch = evaluate_fit_context(
        [criterion],
        [_evidence(criterion.input_fact_key, EvidenceAssertion.ABSENT)],
    )
    unknown = evaluate_fit_context([criterion], [])

    assert match.value is AccountFitContext.MATCH
    assert match.coverage is Coverage.COMPLETE
    assert mismatch.value is AccountFitContext.MISMATCH
    assert unknown.value is AccountFitContext.UNKNOWN
    assert unknown.coverage is Coverage.MISSING


def test_fit_partial_and_inconclusive_preserve_coverage_semantics() -> None:
    first = _criterion("account_profile.first")
    second = _criterion("account_profile.second")
    partial = evaluate_fit_context(
        [first, second],
        [_evidence(first.input_fact_key, EvidenceAssertion.PRESENT)],
    )
    ambiguous = evaluate_fit_context(
        [first],
        [_evidence(first.input_fact_key, EvidenceAssertion.INCONCLUSIVE)],
    )
    contradictory = evaluate_fit_context(
        [first],
        [
            _evidence(first.input_fact_key, EvidenceAssertion.PRESENT),
            _evidence(first.input_fact_key, EvidenceAssertion.ABSENT),
        ],
    )

    assert partial.value is AccountFitContext.PARTIAL
    assert partial.coverage is Coverage.PARTIAL
    assert ambiguous.value is AccountFitContext.INCONCLUSIVE
    assert ambiguous.coverage is Coverage.PARTIAL
    assert contradictory.value is AccountFitContext.INCONCLUSIVE
    assert contradictory.coverage is Coverage.CONTRADICTORY


def test_stale_fit_evidence_does_not_produce_match() -> None:
    criterion = _criterion()

    decision = evaluate_fit_context(
        [criterion],
        [
            _evidence(
                criterion.input_fact_key,
                EvidenceAssertion.PRESENT,
                freshness=EvidenceFreshness.STALE,
            )
        ],
    )

    assert decision.value is AccountFitContext.UNKNOWN
    assert decision.coverage is Coverage.PARTIAL


def test_detected_timing_remains_active_with_missing_other_family() -> None:
    detected_definition = _definition("detected")
    missing_definition = _definition("missing")
    evaluations = [
        _evaluation(
            detected_definition,
            SignalEvaluationResult.DETECTED,
            SignalReasonCode.QUALIFYING_EVENT_WITHIN_WINDOW,
        ),
        _evaluation(
            missing_definition,
            SignalEvaluationResult.INCONCLUSIVE,
            SignalReasonCode.REQUIRED_EVIDENCE_MISSING,
        ),
    ]

    decision = evaluate_timing_state(
        [detected_definition, missing_definition],
        evaluations,
    )

    assert decision.value is AccountTimingState.ACTIVE
    assert decision.coverage is Coverage.PARTIAL


def test_stale_and_no_match_timing_is_stale_with_complete_coverage() -> None:
    stale_definition = _definition("stale")
    absent_definition = _definition("absent")

    decision = evaluate_timing_state(
        [stale_definition, absent_definition],
        [
            _evaluation(
                stale_definition,
                SignalEvaluationResult.STALE,
                SignalReasonCode.QUALIFYING_EVENT_OUTSIDE_WINDOW,
            ),
            _evaluation(
                absent_definition,
                SignalEvaluationResult.NO_MATCH,
                SignalReasonCode.SUFFICIENT_EVIDENCE_NO_EVENT,
            ),
        ],
    )

    assert decision.value is AccountTimingState.STALE
    assert decision.coverage is Coverage.COMPLETE


def test_timing_none_unknown_and_inconclusive_remain_distinct() -> None:
    definition = _definition()
    none = evaluate_timing_state(
        [definition],
        [
            _evaluation(
                definition,
                SignalEvaluationResult.NO_MATCH,
                SignalReasonCode.SUFFICIENT_EVIDENCE_NO_EVENT,
            )
        ],
    )
    unknown = evaluate_timing_state(
        [definition],
        [
            _evaluation(
                definition,
                SignalEvaluationResult.INCONCLUSIVE,
                SignalReasonCode.REQUIRED_EVIDENCE_MISSING,
            )
        ],
    )
    inconclusive = evaluate_timing_state(
        [definition],
        [
            _evaluation(
                definition,
                SignalEvaluationResult.INCONCLUSIVE,
                SignalReasonCode.EVIDENCE_AMBIGUOUS,
            )
        ],
    )

    assert none.value is AccountTimingState.NONE
    assert unknown.value is AccountTimingState.UNKNOWN
    assert unknown.coverage is Coverage.MISSING
    assert inconclusive.value is AccountTimingState.INCONCLUSIVE
    assert inconclusive.coverage is Coverage.PARTIAL


def test_relationship_requires_explicit_absence_for_negative_state() -> None:
    missing = evaluate_relationship_state([])
    absent = evaluate_relationship_state(
        [
            _evidence(
                "relationship.existing_relationship",
                EvidenceAssertion.ABSENT,
            )
        ]
    )
    present = evaluate_relationship_state(
        [
            _evidence(
                "relationship.existing_relationship",
                EvidenceAssertion.PRESENT,
            )
        ]
    )

    assert missing.value is AccountRelationshipState.UNKNOWN
    assert absent.value is AccountRelationshipState.NO_EXISTING_RELATIONSHIP
    assert present.value is AccountRelationshipState.EXISTING_RELATIONSHIP


def test_relationship_ambiguity_and_contradiction_are_not_unknown() -> None:
    ambiguous = evaluate_relationship_state(
        [
            _evidence(
                "relationship.existing_relationship",
                EvidenceAssertion.INCONCLUSIVE,
            )
        ]
    )
    contradictory = evaluate_relationship_state(
        [
            _evidence(
                "relationship.existing_relationship",
                EvidenceAssertion.PRESENT,
            ),
            _evidence(
                "relationship.existing_relationship",
                EvidenceAssertion.ABSENT,
            ),
        ]
    )

    assert ambiguous.value is AccountRelationshipState.INCONCLUSIVE
    assert ambiguous.coverage is Coverage.PARTIAL
    assert contradictory.value is AccountRelationshipState.INCONCLUSIVE
    assert contradictory.coverage is Coverage.CONTRADICTORY


def test_evidence_sufficiency_is_a_categorical_coverage_rollup() -> None:
    sufficient = evaluate_evidence_sufficiency(
        fit=Coverage.COMPLETE,
        timing=Coverage.COMPLETE,
        relationship=Coverage.COMPLETE,
    )
    partial = evaluate_evidence_sufficiency(
        fit=Coverage.COMPLETE,
        timing=Coverage.PARTIAL,
        relationship=Coverage.COMPLETE,
    )
    insufficient = evaluate_evidence_sufficiency(
        fit=Coverage.MISSING,
        timing=Coverage.MISSING,
        relationship=Coverage.MISSING,
    )
    contradictory = evaluate_evidence_sufficiency(
        fit=Coverage.COMPLETE,
        timing=Coverage.CONTRADICTORY,
        relationship=Coverage.COMPLETE,
    )

    assert sufficient.value is AccountEvidenceSufficiency.SUFFICIENT
    assert partial.value is AccountEvidenceSufficiency.PARTIAL
    assert insufficient.value is AccountEvidenceSufficiency.INSUFFICIENT
    assert contradictory.value is AccountEvidenceSufficiency.CONTRADICTORY


def test_hash_ignores_operational_clocks_and_unrelated_evidence() -> None:
    criterion = _criterion()
    source = _strategy_evidence()
    criterion.source_strategy_evidence_id = source.id
    relevant = _evidence(criterion.input_fact_key, EvidenceAssertion.PRESENT)
    unrelated = _evidence("unrelated.account.fact", EvidenceAssertion.PRESENT)
    definition = _definition()
    evaluation = _evaluation(
        definition,
        SignalEvaluationResult.NO_MATCH,
        SignalReasonCode.SUFFICIENT_EVIDENCE_NO_EVENT,
    )

    base = state_input_hash(
        workspace_id=WORKSPACE_ID,
        account_id=ACCOUNT_ID,
        strategy_version_id=STRATEGY_ID,
        state_as_of=AS_OF,
        criteria=[criterion],
        source_evidence={source.id: source},
        account_evidence=[relevant],
        definitions=[definition],
        evaluations=[evaluation],
    )
    evaluation.evaluated_at = evaluation.evaluated_at + timedelta(days=30)
    unchanged = state_input_hash(
        workspace_id=WORKSPACE_ID,
        account_id=ACCOUNT_ID,
        strategy_version_id=STRATEGY_ID,
        state_as_of=AS_OF,
        criteria=[criterion],
        source_evidence={source.id: source},
        account_evidence=[relevant],
        definitions=[definition],
        evaluations=[evaluation],
    )
    still_unchanged = state_input_hash(
        workspace_id=WORKSPACE_ID,
        account_id=ACCOUNT_ID,
        strategy_version_id=STRATEGY_ID,
        state_as_of=AS_OF,
        criteria=[criterion],
        source_evidence={source.id: source},
        account_evidence=[relevant],
        definitions=[definition],
        evaluations=[evaluation],
    )

    assert unrelated.fact_key not in {criterion.input_fact_key}
    assert base == unchanged == still_unchanged


def test_older_relevant_evidence_changes_hash_because_it_is_preserved_as_provenance() -> None:
    criterion = _criterion()
    source = _strategy_evidence()
    criterion.source_strategy_evidence_id = source.id
    current = _evidence(criterion.input_fact_key, EvidenceAssertion.PRESENT)
    older = _evidence(
        criterion.input_fact_key,
        EvidenceAssertion.ABSENT,
        observed_at=AS_OF - timedelta(days=30),
        freshness=EvidenceFreshness.STALE,
    )

    before = state_input_hash(
        workspace_id=WORKSPACE_ID,
        account_id=ACCOUNT_ID,
        strategy_version_id=STRATEGY_ID,
        state_as_of=AS_OF,
        criteria=[criterion],
        source_evidence={source.id: source},
        account_evidence=[current],
        definitions=[],
        evaluations=[],
    )
    after = state_input_hash(
        workspace_id=WORKSPACE_ID,
        account_id=ACCOUNT_ID,
        strategy_version_id=STRATEGY_ID,
        state_as_of=AS_OF,
        criteria=[criterion],
        source_evidence={source.id: source},
        account_evidence=[current, older],
        definitions=[],
        evaluations=[],
    )

    assert before != after
    assert evaluate_fit_context([criterion], [current, older]).value is AccountFitContext.MATCH
