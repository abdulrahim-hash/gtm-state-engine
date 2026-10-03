"""Unit tests for deterministic M1C Decision and Policy semantics."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from gtm_state_api.decision_engine import (
    DECISION_EVALUATOR_REGISTRY,
    POLICY_EVALUATOR_REGISTRY,
    decision_input_hash,
    evaluate_decision_v1,
    evaluate_policy_v1,
    policy_input_hash,
)
from gtm_state_api.models import (
    AccountStateSnapshot,
    DecisionDefinition,
    DecisionEvaluation,
    PolicyDefinition,
)
from gtm_state_api.types import (
    AccountEvidenceSufficiency,
    AccountFitContext,
    AccountRelationshipState,
    AccountTimingState,
    DecisionReasonCode,
    DecisionResult,
    EvaluationDefinitionStatus,
    PolicyReasonCode,
    PolicyResult,
    PolicyTarget,
)

WORKSPACE_ID = UUID("10000000-0000-0000-0000-000000000001")
ACCOUNT_ID = UUID("10000000-0000-0000-0000-000000000002")
STRATEGY_ID = UUID("10000000-0000-0000-0000-000000000003")
SNAPSHOT_ID = UUID("10000000-0000-0000-0000-000000000004")
DECISION_DEFINITION_ID = UUID("10000000-0000-0000-0000-000000000005")
POLICY_DEFINITION_ID = UUID("10000000-0000-0000-0000-000000000006")
AS_OF = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


def _snapshot(
    *,
    snapshot_id: UUID = SNAPSHOT_ID,
    fit: AccountFitContext = AccountFitContext.MATCH,
    timing: AccountTimingState = AccountTimingState.ACTIVE,
    relationship: AccountRelationshipState = AccountRelationshipState.UNKNOWN,
    sufficiency: AccountEvidenceSufficiency = AccountEvidenceSufficiency.PARTIAL,
    computed_at: datetime = AS_OF,
) -> AccountStateSnapshot:
    return AccountStateSnapshot(
        state_snapshot_id=snapshot_id,
        workspace_id=WORKSPACE_ID,
        account_id=ACCOUNT_ID,
        strategy_version_id=STRATEGY_ID,
        state_as_of=AS_OF,
        computed_at=computed_at,
        input_hash="a" * 64,
        state_engine_version="1.0.0",
        fit_context=fit,
        timing_state=timing,
        relationship_state=relationship,
        evidence_sufficiency=sufficiency,
        created_at=computed_at,
    )


def _decision_definition(*, evaluator_version: str = "1.0.0") -> DecisionDefinition:
    return DecisionDefinition(
        decision_definition_id=DECISION_DEFINITION_ID,
        workspace_id=WORKSPACE_ID,
        strategy_version_id=STRATEGY_ID,
        stable_key="default_account_response",
        definition_version="1.0.0",
        display_name="Deterministic account response",
        description="Engagement merits consideration only; this is not an execution command.",
        evaluator_key="fit_timing_response_matrix",
        evaluator_version=evaluator_version,
        status=EvaluationDefinitionStatus.ENABLED,
        created_at=AS_OF,
    )


def _decision(
    snapshot: AccountStateSnapshot,
    *,
    result: DecisionResult = DecisionResult.ENGAGE,
    evaluated_at: datetime = AS_OF,
) -> DecisionEvaluation:
    return DecisionEvaluation(
        decision_evaluation_id=uuid4(),
        workspace_id=snapshot.workspace_id,
        account_id=snapshot.account_id,
        strategy_version_id=snapshot.strategy_version_id,
        state_snapshot_id=snapshot.state_snapshot_id,
        decision_definition_id=DECISION_DEFINITION_ID,
        definition_version="1.0.0",
        evaluated_at=evaluated_at,
        input_hash="b" * 64,
        result=result,
        created_at=evaluated_at,
    )


def _policy_definition(*, evaluator_version: str = "1.0.0") -> PolicyDefinition:
    return PolicyDefinition(
        policy_definition_id=POLICY_DEFINITION_ID,
        workspace_id=WORKSPACE_ID,
        strategy_version_id=STRATEGY_ID,
        stable_key="default_prospecting_guardrails",
        definition_version="1.0.0",
        display_name="Deterministic prospecting guardrails",
        description="Planning gate only; no external action is authorized.",
        target=PolicyTarget.PROSPECTING_ACTIVATION,
        evaluator_key="state_and_relationship_gate",
        evaluator_version=evaluator_version,
        status=EvaluationDefinitionStatus.ENABLED,
        created_at=AS_OF,
    )


def test_registries_pin_code_owned_evaluator_versions() -> None:
    assert tuple(DECISION_EVALUATOR_REGISTRY) == (("fit_timing_response_matrix", "1.0.0"),)
    assert tuple(POLICY_EVALUATOR_REGISTRY) == (("state_and_relationship_gate", "1.0.0"),)


@pytest.mark.parametrize(
    ("relationship", "expected"),
    [
        (AccountRelationshipState.EXISTING_RELATIONSHIP, DecisionResult.ENGAGE),
        (AccountRelationshipState.UNKNOWN, DecisionResult.ENGAGE),
        (AccountRelationshipState.NO_EXISTING_RELATIONSHIP, DecisionResult.ENGAGE),
    ],
)
def test_engage_means_consideration_and_relationship_does_not_change_desirability(
    relationship: AccountRelationshipState,
    expected: DecisionResult,
) -> None:
    output = evaluate_decision_v1(_snapshot(relationship=relationship))

    assert output.result is expected
    assert output.reason_codes == (
        DecisionReasonCode.FIT_MATCH_SUPPORTS_ENGAGEMENT,
        DecisionReasonCode.ACTIVE_TIMING_SUPPORTS_ENGAGEMENT,
    )


@pytest.mark.parametrize(
    ("timing", "reason"),
    [
        (AccountTimingState.NONE, DecisionReasonCode.FIT_MATCH_BUT_NO_CURRENT_TIMING),
        (AccountTimingState.STALE, DecisionReasonCode.FIT_MATCH_BUT_TIMING_STALE),
    ],
)
def test_determinate_non_current_timing_holds(
    timing: AccountTimingState,
    reason: DecisionReasonCode,
) -> None:
    output = evaluate_decision_v1(_snapshot(timing=timing))
    assert output == type(output)(DecisionResult.HOLD, (reason,))


def test_fit_mismatch_produces_no_action() -> None:
    output = evaluate_decision_v1(_snapshot(fit=AccountFitContext.MISMATCH))
    assert output.result is DecisionResult.NO_ACTION
    assert output.reason_codes == (DecisionReasonCode.FIT_MISMATCH_NO_PROSPECTING_BASIS,)


@pytest.mark.parametrize(
    ("snapshot", "reason"),
    [
        (
            _snapshot(fit=AccountFitContext.PARTIAL),
            DecisionReasonCode.FIT_NOT_DETERMINATE,
        ),
        (
            _snapshot(timing=AccountTimingState.INCONCLUSIVE),
            DecisionReasonCode.TIMING_NOT_DETERMINATE,
        ),
        (
            _snapshot(sufficiency=AccountEvidenceSufficiency.INSUFFICIENT),
            DecisionReasonCode.STATE_EVIDENCE_INSUFFICIENT,
        ),
        (
            _snapshot(sufficiency=AccountEvidenceSufficiency.CONTRADICTORY),
            DecisionReasonCode.STATE_EVIDENCE_CONTRADICTORY,
        ),
    ],
)
def test_unresolved_decision_inputs_abstain(
    snapshot: AccountStateSnapshot,
    reason: DecisionReasonCode,
) -> None:
    output = evaluate_decision_v1(snapshot)
    assert output.result is DecisionResult.ABSTAIN
    assert output.reason_codes == (reason,)


def test_asterwind_policy_reason_vector_is_stable() -> None:
    snapshot = _snapshot()
    output = evaluate_policy_v1(snapshot, _decision(snapshot))

    assert output.result is PolicyResult.REQUIRE_REVIEW
    assert output.reason_codes == (
        PolicyReasonCode.RELATIONSHIP_UNKNOWN_REQUIRES_REVIEW,
        PolicyReasonCode.PARTIAL_EVIDENCE_REQUIRES_REVIEW,
    )


def test_cinderlake_policy_reason_vector_is_stable() -> None:
    snapshot = _snapshot(relationship=AccountRelationshipState.EXISTING_RELATIONSHIP)
    output = evaluate_policy_v1(snapshot, _decision(snapshot))

    assert output.result is PolicyResult.REQUIRE_REVIEW
    assert output.reason_codes == (
        PolicyReasonCode.EXISTING_RELATIONSHIP_REQUIRES_CONTROLLED_HANDLING,
        PolicyReasonCode.PARTIAL_EVIDENCE_REQUIRES_REVIEW,
    )


def test_bramble_policy_orders_block_before_review_and_never_emits_allow_support() -> None:
    snapshot = _snapshot(timing=AccountTimingState.INCONCLUSIVE)
    output = evaluate_policy_v1(
        snapshot,
        _decision(snapshot, result=DecisionResult.ABSTAIN),
    )

    assert output.result is PolicyResult.BLOCK
    assert output.reason_codes == (
        PolicyReasonCode.DECISION_DOES_NOT_SUPPORT_ACTIVATION,
        PolicyReasonCode.TIMING_STATE_BLOCKS_ACTIVATION,
        PolicyReasonCode.RELATIONSHIP_UNKNOWN_REQUIRES_REVIEW,
        PolicyReasonCode.PARTIAL_EVIDENCE_REQUIRES_REVIEW,
    )
    assert PolicyReasonCode.ALL_POLICY_CONSTRAINTS_SATISFIED not in output.reason_codes


def test_allow_requires_isolated_explicit_absence_and_sufficient_evidence() -> None:
    snapshot = _snapshot(
        relationship=AccountRelationshipState.NO_EXISTING_RELATIONSHIP,
        sufficiency=AccountEvidenceSufficiency.SUFFICIENT,
    )
    output = evaluate_policy_v1(snapshot, _decision(snapshot))

    assert output.result is PolicyResult.ALLOW
    assert output.reason_codes == (
        PolicyReasonCode.EXPLICIT_NO_EXISTING_RELATIONSHIP,
        PolicyReasonCode.ALL_POLICY_CONSTRAINTS_SATISFIED,
    )


def test_policy_rejects_a_different_snapshot_even_with_matching_facets() -> None:
    snapshot = _snapshot()
    decision = _decision(snapshot)
    other = _snapshot(snapshot_id=uuid4())

    with pytest.raises(ValueError, match="exact state snapshot"):
        evaluate_policy_v1(other, decision)


def test_hashes_exclude_operational_timestamps() -> None:
    first = _snapshot(computed_at=AS_OF)
    second = _snapshot(computed_at=AS_OF + timedelta(days=1))
    definition = _decision_definition()
    assert decision_input_hash(first, definition) == decision_input_hash(second, definition)

    first_decision = _decision(first, evaluated_at=AS_OF)
    second_decision = _decision(first, evaluated_at=AS_OF + timedelta(days=1))
    second_decision.decision_evaluation_id = first_decision.decision_evaluation_id
    assert policy_input_hash(first, first_decision, _policy_definition()) == policy_input_hash(
        first, second_decision, _policy_definition()
    )


def test_relationship_only_snapshot_revision_changes_decision_identity_input() -> None:
    first = _snapshot(relationship=AccountRelationshipState.UNKNOWN)
    second = _snapshot(
        snapshot_id=uuid4(),
        relationship=AccountRelationshipState.NO_EXISTING_RELATIONSHIP,
    )
    definition = _decision_definition()

    assert evaluate_decision_v1(first).result is DecisionResult.ENGAGE
    assert evaluate_decision_v1(second).result is DecisionResult.ENGAGE
    assert decision_input_hash(first, definition) != decision_input_hash(second, definition)


def test_evaluator_versions_change_semantic_hashes() -> None:
    snapshot = _snapshot()
    assert decision_input_hash(snapshot, _decision_definition()) != decision_input_hash(
        snapshot,
        _decision_definition(evaluator_version="2.0.0"),
    )
    decision = _decision(snapshot)
    assert policy_input_hash(snapshot, decision, _policy_definition()) != policy_input_hash(
        snapshot,
        decision,
        _policy_definition(evaluator_version="2.0.0"),
    )
