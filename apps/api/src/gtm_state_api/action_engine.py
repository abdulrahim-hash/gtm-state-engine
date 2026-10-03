"""Deterministic M1D Action derivation from the exact immutable M1C chain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from json import dumps
from uuid import UUID, uuid5

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from gtm_state_api.models import (
    Action,
    DecisionDefinition,
    DecisionEvaluation,
    PolicyDefinition,
    PolicyEvaluation,
    PolicyEvaluationReason,
)
from gtm_state_api.schemas import (
    ActionPayload,
    CreateSellerTaskPayload,
    RequestResearchPayload,
)
from gtm_state_api.types import (
    ActionCurrentProjection,
    ActionType,
    DecisionResult,
    PolicyReasonCode,
    PolicyResult,
    PolicyTarget,
    ResearchRequestCode,
    ResearchTopic,
    SellerTaskKind,
    SellerTaskObjectiveCode,
)

ACTION_NAMESPACE = UUID("1a1206b7-243c-4f22-8d7f-53aa00000a01")
ACTION_INPUT_SCHEMA_VERSION = "1.0.0"
ACTION_SCHEMA_VERSION = "1.0.0"
ACTION_DERIVATION_KEY = "m1c_policy_to_canonical_action"
ACTION_DERIVATION_VERSION = "1.0.0"


@dataclass(frozen=True)
class ActionDerivation:
    """Pure result of evaluating whether M1C supports one M1D Action."""

    projection: ActionCurrentProjection
    action_type: ActionType | None
    payload: ActionPayload | None


def canonical_hash(payload: object) -> str:
    """Return a stable SHA-256 over canonical non-executable JSON."""

    encoded = dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def validate_action_payload(
    action_type: ActionType,
    action_schema_version: str,
    payload: object,
) -> ActionPayload:
    """Validate the strict schema and allowed semantic pair for an Action type."""

    if action_schema_version != ACTION_SCHEMA_VERSION:
        raise ValueError("unsupported Action schema version")
    try:
        if action_type is ActionType.REQUEST_RESEARCH:
            validated = RequestResearchPayload.model_validate(payload)
            allowed = {
                (
                    ResearchTopic.RELATIONSHIP_CONTEXT,
                    ResearchRequestCode.VERIFY_EXISTING_RELATIONSHIP,
                ),
                (
                    ResearchTopic.EVIDENCE_COVERAGE,
                    ResearchRequestCode.RESOLVE_EVIDENCE_GAPS,
                ),
            }
            if (validated.research_topic, validated.request_code) not in allowed:
                raise ValueError("unsupported REQUEST_RESEARCH payload combination")
            return validated
        if action_type is ActionType.CREATE_SELLER_TASK:
            validated_task = CreateSellerTaskPayload.model_validate(payload)
            allowed_tasks = {
                (
                    SellerTaskKind.RELATIONSHIP_COORDINATION,
                    SellerTaskObjectiveCode.ASSESS_CONTROLLED_ENGAGEMENT_PATH,
                ),
                (
                    SellerTaskKind.ENGAGEMENT_ASSESSMENT,
                    SellerTaskObjectiveCode.ASSESS_POLICY_ALLOWED_ENGAGEMENT,
                ),
            }
            if (validated_task.task_kind, validated_task.objective_code) not in allowed_tasks:
                raise ValueError("unsupported CREATE_SELLER_TASK payload combination")
            return validated_task
    except ValidationError as exc:
        raise ValueError("Action payload does not match its strict schema") from exc
    raise ValueError("unsupported Action type")


def derive_action(
    *,
    decision: DecisionEvaluation,
    policy: PolicyEvaluation,
    policy_target: PolicyTarget,
    ordered_reason_codes: tuple[PolicyReasonCode, ...],
) -> ActionDerivation:
    """Map only exact M1C conclusions to zero or one supported Action intent."""

    if policy.decision_evaluation_id != decision.decision_evaluation_id:
        raise ValueError("Policy does not reference the supplied Decision")
    if policy.state_snapshot_id != decision.state_snapshot_id:
        raise ValueError("Policy and Decision do not reference the exact same snapshot")
    if (
        policy.workspace_id != decision.workspace_id
        or policy.account_id != decision.account_id
        or policy.strategy_version_id != decision.strategy_version_id
    ):
        raise ValueError("Policy and Decision scope does not match")
    if policy_target is not PolicyTarget.PROSPECTING_ACTIVATION:
        raise ValueError("unsupported Policy target for Action derivation")
    if policy.result is PolicyResult.BLOCK:
        return ActionDerivation(ActionCurrentProjection.BLOCKED_BY_POLICY, None, None)
    if decision.result is not DecisionResult.ENGAGE:
        raise ValueError("non-BLOCK Policy cannot advance a non-ENGAGE Decision")

    reason_set = set(ordered_reason_codes)
    if policy.result is PolicyResult.ALLOW:
        return ActionDerivation(
            ActionCurrentProjection.ACTION_PROPOSED,
            ActionType.CREATE_SELLER_TASK,
            CreateSellerTaskPayload(
                task_kind=SellerTaskKind.ENGAGEMENT_ASSESSMENT,
                objective_code=SellerTaskObjectiveCode.ASSESS_POLICY_ALLOWED_ENGAGEMENT,
            ),
        )
    if PolicyReasonCode.EXISTING_RELATIONSHIP_REQUIRES_CONTROLLED_HANDLING in reason_set:
        return ActionDerivation(
            ActionCurrentProjection.ACTION_PROPOSED,
            ActionType.CREATE_SELLER_TASK,
            CreateSellerTaskPayload(
                task_kind=SellerTaskKind.RELATIONSHIP_COORDINATION,
                objective_code=SellerTaskObjectiveCode.ASSESS_CONTROLLED_ENGAGEMENT_PATH,
            ),
        )
    if reason_set.intersection(
        {
            PolicyReasonCode.RELATIONSHIP_UNKNOWN_REQUIRES_REVIEW,
            PolicyReasonCode.RELATIONSHIP_INCONCLUSIVE_REQUIRES_REVIEW,
        }
    ):
        return ActionDerivation(
            ActionCurrentProjection.ACTION_PROPOSED,
            ActionType.REQUEST_RESEARCH,
            RequestResearchPayload(
                research_topic=ResearchTopic.RELATIONSHIP_CONTEXT,
                request_code=ResearchRequestCode.VERIFY_EXISTING_RELATIONSHIP,
            ),
        )
    if PolicyReasonCode.PARTIAL_EVIDENCE_REQUIRES_REVIEW in reason_set:
        return ActionDerivation(
            ActionCurrentProjection.ACTION_PROPOSED,
            ActionType.REQUEST_RESEARCH,
            RequestResearchPayload(
                research_topic=ResearchTopic.EVIDENCE_COVERAGE,
                request_code=ResearchRequestCode.RESOLVE_EVIDENCE_GAPS,
            ),
        )
    return ActionDerivation(ActionCurrentProjection.NO_SUPPORTED_ACTION, None, None)


def policy_chain(
    session: Session,
    policy_evaluation_id: UUID,
) -> tuple[
    PolicyEvaluation,
    PolicyDefinition,
    DecisionEvaluation,
    DecisionDefinition,
    tuple[PolicyReasonCode, ...],
]:
    """Load only the exact immutable M1C chain used by Action derivation."""

    policy = session.get(PolicyEvaluation, policy_evaluation_id)
    if policy is None:
        raise ValueError("Policy evaluation not found")
    policy_definition = session.get(PolicyDefinition, policy.policy_definition_id)
    decision = session.get(DecisionEvaluation, policy.decision_evaluation_id)
    if policy_definition is None or decision is None:
        raise ValueError("Policy evaluation has incomplete M1C provenance")
    decision_definition = session.get(DecisionDefinition, decision.decision_definition_id)
    if decision_definition is None:
        raise ValueError("Decision evaluation definition is missing")
    reason_rows = session.scalars(
        select(PolicyEvaluationReason)
        .where(PolicyEvaluationReason.policy_evaluation_id == policy.policy_evaluation_id)
        .order_by(PolicyEvaluationReason.position)
    ).all()
    return (
        policy,
        policy_definition,
        decision,
        decision_definition,
        tuple(row.reason_code for row in reason_rows),
    )


def action_semantic_input(
    *,
    policy: PolicyEvaluation,
    policy_definition: PolicyDefinition,
    decision: DecisionEvaluation,
    decision_definition: DecisionDefinition,
    ordered_reason_codes: tuple[PolicyReasonCode, ...],
    action_type: ActionType,
    payload: ActionPayload,
) -> dict[str, object]:
    """Build the full-chain semantic attestation for one Action proposal."""

    return {
        "input_schema_version": ACTION_INPUT_SCHEMA_VERSION,
        "workspace_id": str(policy.workspace_id),
        "account_id": str(policy.account_id),
        "strategy_version_id": str(policy.strategy_version_id),
        "state_snapshot_id": str(policy.state_snapshot_id),
        "decision": {
            "decision_evaluation_id": str(decision.decision_evaluation_id),
            "input_hash": decision.input_hash,
            "result": decision.result.value,
            "decision_definition_id": str(decision_definition.decision_definition_id),
            "definition_version": decision_definition.definition_version,
            "evaluator_key": decision_definition.evaluator_key,
            "evaluator_version": decision_definition.evaluator_version,
        },
        "policy": {
            "policy_evaluation_id": str(policy.policy_evaluation_id),
            "input_hash": policy.input_hash,
            "result": policy.result.value,
            "reason_codes": [reason.value for reason in ordered_reason_codes],
            "policy_definition_id": str(policy_definition.policy_definition_id),
            "definition_version": policy_definition.definition_version,
            "target": policy_definition.target.value,
            "evaluator_key": policy_definition.evaluator_key,
            "evaluator_version": policy_definition.evaluator_version,
        },
        "derivation": {
            "key": ACTION_DERIVATION_KEY,
            "version": ACTION_DERIVATION_VERSION,
        },
        "action": {
            "action_type": action_type.value,
            "action_schema_version": ACTION_SCHEMA_VERSION,
            "payload": payload.model_dump(mode="json"),
        },
    }


def _validate_existing_action(
    action: Action,
    *,
    input_hash: str,
    action_type: ActionType,
    payload: ActionPayload,
) -> None:
    validated = validate_action_payload(
        action.action_type,
        action.action_schema_version,
        action.payload,
    )
    if (
        action.semantic_input_hash != input_hash
        or action.action_type is not action_type
        or action.derivation_key != ACTION_DERIVATION_KEY
        or action.derivation_version != ACTION_DERIVATION_VERSION
        or validated.model_dump(mode="json") != payload.model_dump(mode="json")
    ):
        raise ValueError("existing Action does not match deterministic output")


def materialize_policy_action(
    session: Session,
    policy_evaluation_id: UUID,
    *,
    proposed_at: datetime | None = None,
) -> tuple[ActionCurrentProjection, Action | None]:
    """Materialize zero or one idempotent Action for an exact Policy evaluation."""

    (
        policy,
        policy_definition,
        decision,
        decision_definition,
        ordered_reasons,
    ) = policy_chain(session, policy_evaluation_id)
    derivation = derive_action(
        decision=decision,
        policy=policy,
        policy_target=policy_definition.target,
        ordered_reason_codes=ordered_reasons,
    )
    if derivation.action_type is None or derivation.payload is None:
        return derivation.projection, None

    validated_payload = validate_action_payload(
        derivation.action_type,
        ACTION_SCHEMA_VERSION,
        derivation.payload.model_dump(mode="json"),
    )
    semantic_input = action_semantic_input(
        policy=policy,
        policy_definition=policy_definition,
        decision=decision,
        decision_definition=decision_definition,
        ordered_reason_codes=ordered_reasons,
        action_type=derivation.action_type,
        payload=validated_payload,
    )
    input_hash = canonical_hash(semantic_input)
    action_id = uuid5(ACTION_NAMESPACE, input_hash)
    existing = session.get(Action, action_id)
    if existing is not None:
        _validate_existing_action(
            existing,
            input_hash=input_hash,
            action_type=derivation.action_type,
            payload=validated_payload,
        )
        return derivation.projection, existing

    execution_time = proposed_at or datetime.now(UTC)
    action = Action(
        action_id=action_id,
        workspace_id=policy.workspace_id,
        account_id=policy.account_id,
        strategy_version_id=policy.strategy_version_id,
        policy_evaluation_id=policy.policy_evaluation_id,
        action_type=derivation.action_type,
        action_schema_version=ACTION_SCHEMA_VERSION,
        derivation_key=ACTION_DERIVATION_KEY,
        derivation_version=ACTION_DERIVATION_VERSION,
        payload=validated_payload.model_dump(mode="json"),
        semantic_input_hash=input_hash,
        proposed_at=execution_time,
        created_at=execution_time,
    )
    try:
        with session.begin_nested():
            session.add(action)
            session.flush()
    except IntegrityError:
        existing = session.get(Action, action_id)
        if existing is None:
            raise
        _validate_existing_action(
            existing,
            input_hash=input_hash,
            action_type=derivation.action_type,
            payload=validated_payload,
        )
        return derivation.projection, existing
    return derivation.projection, action


def materialize_policy_actions(
    session: Session,
    policy_evaluation_ids: list[UUID],
    *,
    proposed_at: datetime | None = None,
) -> list[tuple[ActionCurrentProjection, Action | None]]:
    """Materialize M1D only for the explicit immutable Policy IDs supplied."""

    return [
        materialize_policy_action(session, policy_id, proposed_at=proposed_at)
        for policy_id in policy_evaluation_ids
    ]
