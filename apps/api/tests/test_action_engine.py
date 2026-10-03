"""Unit tests for deterministic M1D Action derivation and authority boundaries."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from gtm_state_api.action_engine import (
    ACTION_SCHEMA_VERSION,
    action_semantic_input,
    canonical_hash,
    derive_action,
    validate_action_payload,
)
from gtm_state_api.config import Settings
from gtm_state_api.models import (
    DecisionDefinition,
    DecisionEvaluation,
    PolicyDefinition,
    PolicyEvaluation,
)
from gtm_state_api.schemas import ActionReviewRequest, RequestResearchPayload
from gtm_state_api.types import (
    ActionCurrentProjection,
    ActionReviewReasonCode,
    ActionReviewResolution,
    ActionType,
    DecisionResult,
    EvaluationDefinitionStatus,
    PolicyReasonCode,
    PolicyResult,
    PolicyTarget,
    ResearchRequestCode,
    ResearchTopic,
)

TIME = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
WORKSPACE_ID = UUID("1a1206b7-243c-4f22-8d7f-53aa00000001")
ACCOUNT_ID = UUID("1a1206b7-243c-4f22-8d7f-53aa00000011")
STRATEGY_ID = UUID("1a1206b7-243c-4f22-8d7f-53aa00000002")
SNAPSHOT_ID = UUID("1a1206b7-243c-4f22-8d7f-53aa00000e01")


def _chain(
    *,
    decision_result: DecisionResult = DecisionResult.ENGAGE,
    policy_result: PolicyResult = PolicyResult.REQUIRE_REVIEW,
    policy_id: UUID | None = None,
) -> tuple[
    DecisionEvaluation,
    PolicyEvaluation,
    DecisionDefinition,
    PolicyDefinition,
]:
    decision_definition = DecisionDefinition(
        decision_definition_id=uuid4(),
        workspace_id=WORKSPACE_ID,
        strategy_version_id=STRATEGY_ID,
        stable_key="test_decision",
        definition_version="1.0.0",
        display_name="Test Decision",
        description="Test",
        evaluator_key="test_decision",
        evaluator_version="1.0.0",
        status=EvaluationDefinitionStatus.ENABLED,
        created_at=TIME,
    )
    policy_definition = PolicyDefinition(
        policy_definition_id=uuid4(),
        workspace_id=WORKSPACE_ID,
        strategy_version_id=STRATEGY_ID,
        stable_key="test_policy",
        definition_version="1.0.0",
        display_name="Test Policy",
        description="Test",
        target=PolicyTarget.PROSPECTING_ACTIVATION,
        evaluator_key="test_policy",
        evaluator_version="1.0.0",
        status=EvaluationDefinitionStatus.ENABLED,
        created_at=TIME,
    )
    decision = DecisionEvaluation(
        decision_evaluation_id=uuid4(),
        workspace_id=WORKSPACE_ID,
        account_id=ACCOUNT_ID,
        strategy_version_id=STRATEGY_ID,
        state_snapshot_id=SNAPSHOT_ID,
        decision_definition_id=decision_definition.decision_definition_id,
        definition_version="1.0.0",
        evaluated_at=TIME,
        input_hash="a" * 64,
        result=decision_result,
        created_at=TIME,
    )
    policy = PolicyEvaluation(
        policy_evaluation_id=policy_id or uuid4(),
        workspace_id=WORKSPACE_ID,
        account_id=ACCOUNT_ID,
        strategy_version_id=STRATEGY_ID,
        state_snapshot_id=SNAPSHOT_ID,
        decision_evaluation_id=decision.decision_evaluation_id,
        policy_definition_id=policy_definition.policy_definition_id,
        definition_version="1.0.0",
        evaluated_at=TIME,
        input_hash="b" * 64,
        result=policy_result,
        created_at=TIME,
    )
    return decision, policy, decision_definition, policy_definition


def test_action_mapping_uses_only_exact_m1c_results_and_reasons() -> None:
    decision, policy, _, _ = _chain()
    asterwind = derive_action(
        decision=decision,
        policy=policy,
        policy_target=PolicyTarget.PROSPECTING_ACTIVATION,
        ordered_reason_codes=(
            PolicyReasonCode.RELATIONSHIP_UNKNOWN_REQUIRES_REVIEW,
            PolicyReasonCode.PARTIAL_EVIDENCE_REQUIRES_REVIEW,
        ),
    )
    assert asterwind.projection is ActionCurrentProjection.ACTION_PROPOSED
    assert asterwind.action_type is ActionType.REQUEST_RESEARCH
    assert asterwind.payload == RequestResearchPayload(
        research_topic=ResearchTopic.RELATIONSHIP_CONTEXT,
        request_code=ResearchRequestCode.VERIFY_EXISTING_RELATIONSHIP,
    )

    cinderlake = derive_action(
        decision=decision,
        policy=policy,
        policy_target=PolicyTarget.PROSPECTING_ACTIVATION,
        ordered_reason_codes=(
            PolicyReasonCode.EXISTING_RELATIONSHIP_REQUIRES_CONTROLLED_HANDLING,
            PolicyReasonCode.PARTIAL_EVIDENCE_REQUIRES_REVIEW,
        ),
    )
    assert cinderlake.action_type is ActionType.CREATE_SELLER_TASK
    assert cinderlake.payload is not None
    assert cinderlake.payload.model_dump()["task_kind"] == "RELATIONSHIP_COORDINATION"

    decision.result = DecisionResult.ABSTAIN
    policy.result = PolicyResult.BLOCK
    blocked = derive_action(
        decision=decision,
        policy=policy,
        policy_target=PolicyTarget.PROSPECTING_ACTIVATION,
        ordered_reason_codes=(PolicyReasonCode.DECISION_DOES_NOT_SUPPORT_ACTIVATION,),
    )
    assert blocked.projection is ActionCurrentProjection.BLOCKED_BY_POLICY
    assert blocked.action_type is blocked.payload is None


def test_unsupported_review_reason_abstains_and_allow_remains_local_only() -> None:
    decision, policy, _, _ = _chain()
    unsupported = derive_action(
        decision=decision,
        policy=policy,
        policy_target=PolicyTarget.PROSPECTING_ACTIVATION,
        ordered_reason_codes=(),
    )
    assert unsupported.projection is ActionCurrentProjection.NO_SUPPORTED_ACTION
    assert unsupported.payload is None

    policy.result = PolicyResult.ALLOW
    allowed = derive_action(
        decision=decision,
        policy=policy,
        policy_target=PolicyTarget.PROSPECTING_ACTIVATION,
        ordered_reason_codes=(
            PolicyReasonCode.EXPLICIT_NO_EXISTING_RELATIONSHIP,
            PolicyReasonCode.ALL_POLICY_CONSTRAINTS_SATISFIED,
        ),
    )
    assert allowed.action_type is ActionType.CREATE_SELLER_TASK
    assert allowed.payload is not None
    assert allowed.payload.model_dump()["task_kind"] == "ENGAGEMENT_ASSESSMENT"


def test_mismatched_chain_fails_closed() -> None:
    decision, policy, _, _ = _chain()
    policy.state_snapshot_id = uuid4()
    with pytest.raises(ValueError, match="exact same snapshot"):
        derive_action(
            decision=decision,
            policy=policy,
            policy_target=PolicyTarget.PROSPECTING_ACTIVATION,
            ordered_reason_codes=(),
        )


def test_canonical_payload_is_bounded_and_key_order_does_not_change_hash() -> None:
    first = {
        "research_topic": "RELATIONSHIP_CONTEXT",
        "request_code": "VERIFY_EXISTING_RELATIONSHIP",
    }
    second = dict(reversed(list(first.items())))
    assert canonical_hash(first) == canonical_hash(second)
    assert validate_action_payload(ActionType.REQUEST_RESEARCH, ACTION_SCHEMA_VERSION, first)
    with pytest.raises(ValueError, match="strict schema"):
        validate_action_payload(
            ActionType.REQUEST_RESEARCH,
            ACTION_SCHEMA_VERSION,
            {**first, "provider": "hubspot"},
        )
    with pytest.raises(ValueError, match="unsupported Action schema version"):
        validate_action_payload(ActionType.REQUEST_RESEARCH, "2.0.0", first)


def test_policy_identity_changes_full_chain_action_hash() -> None:
    decision, policy, decision_definition, policy_definition = _chain()
    payload = RequestResearchPayload(
        research_topic=ResearchTopic.RELATIONSHIP_CONTEXT,
        request_code=ResearchRequestCode.VERIFY_EXISTING_RELATIONSHIP,
    )
    first = action_semantic_input(
        policy=policy,
        policy_definition=policy_definition,
        decision=decision,
        decision_definition=decision_definition,
        ordered_reason_codes=(PolicyReasonCode.RELATIONSHIP_UNKNOWN_REQUIRES_REVIEW,),
        action_type=ActionType.REQUEST_RESEARCH,
        payload=payload,
    )
    policy.policy_evaluation_id = uuid4()
    second = action_semantic_input(
        policy=policy,
        policy_definition=policy_definition,
        decision=decision,
        decision_definition=decision_definition,
        ordered_reason_codes=(PolicyReasonCode.RELATIONSHIP_UNKNOWN_REQUIRES_REVIEW,),
        action_type=ActionType.REQUEST_RESEARCH,
        payload=payload,
    )
    assert canonical_hash(first) != canonical_hash(second)
    assert "evaluated_at" not in first
    assert "created_at" not in first


def test_review_request_forbids_actor_claims_and_invalid_reason() -> None:
    with pytest.raises(ValidationError):
        ActionReviewRequest.model_validate(
            {
                "resolution": "APPROVED",
                "reason_code": "APPROVED_AS_PROPOSED",
                "reviewer_email": "not-allowed@example.test",
            }
        )
    with pytest.raises(ValidationError):
        ActionReviewRequest(
            resolution=ActionReviewResolution.APPROVED,
            reason_code=ActionReviewReasonCode.REJECTED_INSUFFICIENT_CONTEXT,
        )


def test_production_configuration_rejects_action_mutations() -> None:
    with pytest.raises(ValidationError, match="ACTION_MUTATIONS_ENABLED"):
        Settings(app_env="production", action_mutations_enabled=True)
    assert Settings(app_env="production").action_mutations_enabled is False
