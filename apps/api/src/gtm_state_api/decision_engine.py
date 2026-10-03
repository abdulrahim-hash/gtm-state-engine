"""Deterministic M1C Decision and Policy evaluation over immutable account state."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from json import dumps
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from gtm_state_api.models import (
    AccountStateSnapshot,
    DecisionDefinition,
    DecisionEvaluation,
    DecisionEvaluationReason,
    PolicyDefinition,
    PolicyEvaluation,
    PolicyEvaluationReason,
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

DECISION_EVALUATION_NAMESPACE = UUID("1a1206b7-243c-4f22-8d7f-53aa00000801")
POLICY_EVALUATION_NAMESPACE = UUID("1a1206b7-243c-4f22-8d7f-53aa00000901")
DECISION_INPUT_SCHEMA_VERSION = "1.0.0"
POLICY_INPUT_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class DecisionOutput:
    """Pure deterministic Decision result and its stable ordered reasons."""

    result: DecisionResult
    reason_codes: tuple[DecisionReasonCode, ...]


@dataclass(frozen=True)
class PolicyOutput:
    """Pure deterministic Policy result and its stable ordered constraints."""

    result: PolicyResult
    reason_codes: tuple[PolicyReasonCode, ...]


DecisionEvaluator = Callable[[AccountStateSnapshot], DecisionOutput]
PolicyEvaluator = Callable[[AccountStateSnapshot, DecisionEvaluation], PolicyOutput]


def evaluate_decision_v1(snapshot: AccountStateSnapshot) -> DecisionOutput:
    """Determine whether engagement merits consideration without proposing an action."""

    if snapshot.evidence_sufficiency is AccountEvidenceSufficiency.CONTRADICTORY:
        return DecisionOutput(
            result=DecisionResult.ABSTAIN,
            reason_codes=(DecisionReasonCode.STATE_EVIDENCE_CONTRADICTORY,),
        )
    if snapshot.evidence_sufficiency is AccountEvidenceSufficiency.INSUFFICIENT:
        return DecisionOutput(
            result=DecisionResult.ABSTAIN,
            reason_codes=(DecisionReasonCode.STATE_EVIDENCE_INSUFFICIENT,),
        )
    if snapshot.fit_context in {
        AccountFitContext.PARTIAL,
        AccountFitContext.UNKNOWN,
        AccountFitContext.INCONCLUSIVE,
    }:
        return DecisionOutput(
            result=DecisionResult.ABSTAIN,
            reason_codes=(DecisionReasonCode.FIT_NOT_DETERMINATE,),
        )
    if snapshot.fit_context is AccountFitContext.MISMATCH:
        return DecisionOutput(
            result=DecisionResult.NO_ACTION,
            reason_codes=(DecisionReasonCode.FIT_MISMATCH_NO_PROSPECTING_BASIS,),
        )
    if snapshot.timing_state is AccountTimingState.ACTIVE:
        return DecisionOutput(
            result=DecisionResult.ENGAGE,
            reason_codes=(
                DecisionReasonCode.FIT_MATCH_SUPPORTS_ENGAGEMENT,
                DecisionReasonCode.ACTIVE_TIMING_SUPPORTS_ENGAGEMENT,
            ),
        )
    if snapshot.timing_state is AccountTimingState.NONE:
        return DecisionOutput(
            result=DecisionResult.HOLD,
            reason_codes=(DecisionReasonCode.FIT_MATCH_BUT_NO_CURRENT_TIMING,),
        )
    if snapshot.timing_state is AccountTimingState.STALE:
        return DecisionOutput(
            result=DecisionResult.HOLD,
            reason_codes=(DecisionReasonCode.FIT_MATCH_BUT_TIMING_STALE,),
        )
    return DecisionOutput(
        result=DecisionResult.ABSTAIN,
        reason_codes=(DecisionReasonCode.TIMING_NOT_DETERMINATE,),
    )


def evaluate_policy_v1(
    snapshot: AccountStateSnapshot,
    decision: DecisionEvaluation,
) -> PolicyOutput:
    """Gate future prospecting activation without authorizing any external action."""

    if decision.state_snapshot_id != snapshot.state_snapshot_id:
        raise ValueError("policy input must use the Decision's exact state snapshot")
    if (
        decision.workspace_id != snapshot.workspace_id
        or decision.account_id != snapshot.account_id
        or decision.strategy_version_id != snapshot.strategy_version_id
    ):
        raise ValueError("policy input scope does not match the Decision and state snapshot")

    block_reasons: list[PolicyReasonCode] = []
    review_reasons: list[PolicyReasonCode] = []

    if decision.result is not DecisionResult.ENGAGE:
        block_reasons.append(PolicyReasonCode.DECISION_DOES_NOT_SUPPORT_ACTIVATION)
    if snapshot.fit_context is not AccountFitContext.MATCH:
        block_reasons.append(PolicyReasonCode.FIT_STATE_BLOCKS_ACTIVATION)
    if snapshot.timing_state is not AccountTimingState.ACTIVE:
        block_reasons.append(PolicyReasonCode.TIMING_STATE_BLOCKS_ACTIVATION)
    if snapshot.evidence_sufficiency is AccountEvidenceSufficiency.INSUFFICIENT:
        block_reasons.append(PolicyReasonCode.EVIDENCE_INSUFFICIENT_BLOCKS_ACTIVATION)
    if snapshot.evidence_sufficiency is AccountEvidenceSufficiency.CONTRADICTORY:
        block_reasons.append(PolicyReasonCode.EVIDENCE_CONTRADICTORY_BLOCKS_ACTIVATION)

    engagement_state_is_consistent = (
        snapshot.fit_context is AccountFitContext.MATCH
        and snapshot.timing_state is AccountTimingState.ACTIVE
        and snapshot.evidence_sufficiency
        not in {
            AccountEvidenceSufficiency.INSUFFICIENT,
            AccountEvidenceSufficiency.CONTRADICTORY,
        }
    )
    if (decision.result is DecisionResult.ENGAGE) is not engagement_state_is_consistent:
        block_reasons.append(PolicyReasonCode.DECISION_STATE_MISMATCH)

    if snapshot.relationship_state is AccountRelationshipState.EXISTING_RELATIONSHIP:
        review_reasons.append(PolicyReasonCode.EXISTING_RELATIONSHIP_REQUIRES_CONTROLLED_HANDLING)
    elif snapshot.relationship_state is AccountRelationshipState.UNKNOWN:
        review_reasons.append(PolicyReasonCode.RELATIONSHIP_UNKNOWN_REQUIRES_REVIEW)
    elif snapshot.relationship_state is AccountRelationshipState.INCONCLUSIVE:
        review_reasons.append(PolicyReasonCode.RELATIONSHIP_INCONCLUSIVE_REQUIRES_REVIEW)

    if snapshot.evidence_sufficiency is AccountEvidenceSufficiency.PARTIAL:
        review_reasons.append(PolicyReasonCode.PARTIAL_EVIDENCE_REQUIRES_REVIEW)

    if block_reasons:
        return PolicyOutput(
            result=PolicyResult.BLOCK,
            reason_codes=tuple([*block_reasons, *review_reasons]),
        )
    if review_reasons:
        return PolicyOutput(
            result=PolicyResult.REQUIRE_REVIEW,
            reason_codes=tuple(review_reasons),
        )
    return PolicyOutput(
        result=PolicyResult.ALLOW,
        reason_codes=(
            PolicyReasonCode.EXPLICIT_NO_EXISTING_RELATIONSHIP,
            PolicyReasonCode.ALL_POLICY_CONSTRAINTS_SATISFIED,
        ),
    )


DECISION_EVALUATOR_REGISTRY: Mapping[tuple[str, str], DecisionEvaluator] = {
    ("fit_timing_response_matrix", "1.0.0"): evaluate_decision_v1,
}

POLICY_EVALUATOR_REGISTRY: Mapping[tuple[str, str], PolicyEvaluator] = {
    ("state_and_relationship_gate", "1.0.0"): evaluate_policy_v1,
}


def _canonical_hash(payload: object) -> str:
    encoded = dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def _snapshot_hash_input(snapshot: AccountStateSnapshot) -> dict[str, str]:
    return {
        "evidence_sufficiency": snapshot.evidence_sufficiency.value,
        "fit_context": snapshot.fit_context.value,
        "input_hash": snapshot.input_hash,
        "relationship_state": snapshot.relationship_state.value,
        "state_as_of": snapshot.state_as_of.isoformat(),
        "state_engine_version": snapshot.state_engine_version,
        "state_snapshot_id": str(snapshot.state_snapshot_id),
        "timing_state": snapshot.timing_state.value,
    }


def decision_input_hash(
    snapshot: AccountStateSnapshot,
    definition: DecisionDefinition,
) -> str:
    """Hash the exact snapshot attestation and code-owned Decision definition."""

    return _canonical_hash(
        {
            "account_id": str(snapshot.account_id),
            "definition": {
                "decision_definition_id": str(definition.decision_definition_id),
                "definition_version": definition.definition_version,
                "evaluator_key": definition.evaluator_key,
                "evaluator_version": definition.evaluator_version,
                "stable_key": definition.stable_key,
            },
            "input_schema_version": DECISION_INPUT_SCHEMA_VERSION,
            "state_snapshot": _snapshot_hash_input(snapshot),
            "strategy_version_id": str(snapshot.strategy_version_id),
            "workspace_id": str(snapshot.workspace_id),
        }
    )


def policy_input_hash(
    snapshot: AccountStateSnapshot,
    decision: DecisionEvaluation,
    definition: PolicyDefinition,
) -> str:
    """Hash the exact Decision, snapshot attestation, and Policy definition."""

    return _canonical_hash(
        {
            "account_id": str(snapshot.account_id),
            "decision": {
                "decision_evaluation_id": str(decision.decision_evaluation_id),
                "input_hash": decision.input_hash,
                "result": decision.result.value,
            },
            "input_schema_version": POLICY_INPUT_SCHEMA_VERSION,
            "policy_definition": {
                "definition_version": definition.definition_version,
                "evaluator_key": definition.evaluator_key,
                "evaluator_version": definition.evaluator_version,
                "policy_definition_id": str(definition.policy_definition_id),
                "stable_key": definition.stable_key,
                "target": definition.target.value,
            },
            "state_snapshot": _snapshot_hash_input(snapshot),
            "strategy_version_id": str(snapshot.strategy_version_id),
            "workspace_id": str(snapshot.workspace_id),
        }
    )


def _enabled_decision_definition(
    session: Session,
    snapshot: AccountStateSnapshot,
) -> DecisionDefinition:
    definitions = session.scalars(
        select(DecisionDefinition).where(
            DecisionDefinition.workspace_id == snapshot.workspace_id,
            DecisionDefinition.strategy_version_id == snapshot.strategy_version_id,
            DecisionDefinition.status == EvaluationDefinitionStatus.ENABLED,
        )
    ).all()
    if len(definitions) != 1:
        raise ValueError("materialization requires exactly one enabled Decision definition")
    return definitions[0]


def _enabled_policy_definition(
    session: Session,
    snapshot: AccountStateSnapshot,
) -> PolicyDefinition:
    definitions = session.scalars(
        select(PolicyDefinition).where(
            PolicyDefinition.workspace_id == snapshot.workspace_id,
            PolicyDefinition.strategy_version_id == snapshot.strategy_version_id,
            PolicyDefinition.target == PolicyTarget.PROSPECTING_ACTIVATION,
            PolicyDefinition.status == EvaluationDefinitionStatus.ENABLED,
        )
    ).all()
    if len(definitions) != 1:
        raise ValueError("materialization requires exactly one enabled Policy definition")
    return definitions[0]


def _decision_definition(
    session: Session,
    snapshot: AccountStateSnapshot,
) -> DecisionDefinition:
    definition = _enabled_decision_definition(session, snapshot)
    if (definition.evaluator_key, definition.evaluator_version) not in DECISION_EVALUATOR_REGISTRY:
        raise ValueError("Decision definition selects an unsupported evaluator")
    return definition


def _policy_definition(
    session: Session,
    snapshot: AccountStateSnapshot,
) -> PolicyDefinition:
    definition = _enabled_policy_definition(session, snapshot)
    if (definition.evaluator_key, definition.evaluator_version) not in POLICY_EVALUATOR_REGISTRY:
        raise ValueError("Policy definition selects an unsupported evaluator")
    return definition


def _validate_existing_decision(
    session: Session,
    evaluation: DecisionEvaluation,
    *,
    input_hash: str,
    output: DecisionOutput,
) -> None:
    if evaluation.input_hash != input_hash or evaluation.result is not output.result:
        raise ValueError("existing Decision evaluation does not match deterministic output")
    reasons = session.scalars(
        select(DecisionEvaluationReason)
        .where(DecisionEvaluationReason.decision_evaluation_id == evaluation.decision_evaluation_id)
        .order_by(DecisionEvaluationReason.position)
    ).all()
    if tuple(item.reason_code for item in reasons) != output.reason_codes:
        raise ValueError("existing Decision reasons do not match deterministic output")


def _validate_existing_policy(
    session: Session,
    evaluation: PolicyEvaluation,
    *,
    input_hash: str,
    output: PolicyOutput,
) -> None:
    if evaluation.input_hash != input_hash or evaluation.result is not output.result:
        raise ValueError("existing Policy evaluation does not match deterministic output")
    reasons = session.scalars(
        select(PolicyEvaluationReason)
        .where(PolicyEvaluationReason.policy_evaluation_id == evaluation.policy_evaluation_id)
        .order_by(PolicyEvaluationReason.position)
    ).all()
    if tuple(item.reason_code for item in reasons) != output.reason_codes:
        raise ValueError("existing Policy reasons do not match deterministic output")


def materialize_decision_evaluation(
    session: Session,
    state_snapshot_id: UUID,
    *,
    evaluated_at: datetime | None = None,
) -> DecisionEvaluation:
    """Materialize one idempotent Decision for an explicit immutable snapshot ID."""

    snapshot = session.get(AccountStateSnapshot, state_snapshot_id)
    if snapshot is None:
        raise ValueError("account state snapshot not found")
    definition = _decision_definition(session, snapshot)
    evaluator = DECISION_EVALUATOR_REGISTRY[
        (
            definition.evaluator_key,
            definition.evaluator_version,
        )
    ]
    output = evaluator(snapshot)
    input_hash = decision_input_hash(snapshot, definition)
    evaluation_id = uuid5(DECISION_EVALUATION_NAMESPACE, input_hash)
    existing = session.get(DecisionEvaluation, evaluation_id)
    if existing is not None:
        _validate_existing_decision(session, existing, input_hash=input_hash, output=output)
        return existing

    execution_time = evaluated_at or datetime.now(UTC)
    evaluation = DecisionEvaluation(
        decision_evaluation_id=evaluation_id,
        workspace_id=snapshot.workspace_id,
        account_id=snapshot.account_id,
        strategy_version_id=snapshot.strategy_version_id,
        state_snapshot_id=snapshot.state_snapshot_id,
        decision_definition_id=definition.decision_definition_id,
        definition_version=definition.definition_version,
        evaluated_at=execution_time,
        input_hash=input_hash,
        result=output.result,
        created_at=execution_time,
    )
    try:
        with session.begin_nested():
            session.add(evaluation)
            session.flush()
            session.add_all(
                [
                    DecisionEvaluationReason(
                        decision_evaluation_id=evaluation_id,
                        position=position,
                        reason_code=reason,
                    )
                    for position, reason in enumerate(output.reason_codes)
                ]
            )
            session.flush()
    except IntegrityError:
        existing = session.get(DecisionEvaluation, evaluation_id)
        if existing is None:
            raise
        _validate_existing_decision(session, existing, input_hash=input_hash, output=output)
        return existing
    return evaluation


def materialize_policy_evaluation(
    session: Session,
    decision_evaluation_id: UUID,
    *,
    evaluated_at: datetime | None = None,
) -> PolicyEvaluation:
    """Materialize one idempotent Policy for a Decision and its exact snapshot."""

    decision = session.get(DecisionEvaluation, decision_evaluation_id)
    if decision is None:
        raise ValueError("Decision evaluation not found")
    snapshot = session.get(AccountStateSnapshot, decision.state_snapshot_id)
    if snapshot is None:
        raise ValueError("Decision state snapshot not found")
    definition = _policy_definition(session, snapshot)
    evaluator = POLICY_EVALUATOR_REGISTRY[
        (
            definition.evaluator_key,
            definition.evaluator_version,
        )
    ]
    output = evaluator(snapshot, decision)
    input_hash = policy_input_hash(snapshot, decision, definition)
    evaluation_id = uuid5(POLICY_EVALUATION_NAMESPACE, input_hash)
    existing = session.get(PolicyEvaluation, evaluation_id)
    if existing is not None:
        _validate_existing_policy(session, existing, input_hash=input_hash, output=output)
        return existing

    execution_time = evaluated_at or datetime.now(UTC)
    evaluation = PolicyEvaluation(
        policy_evaluation_id=evaluation_id,
        workspace_id=snapshot.workspace_id,
        account_id=snapshot.account_id,
        strategy_version_id=snapshot.strategy_version_id,
        state_snapshot_id=snapshot.state_snapshot_id,
        decision_evaluation_id=decision.decision_evaluation_id,
        policy_definition_id=definition.policy_definition_id,
        definition_version=definition.definition_version,
        evaluated_at=execution_time,
        input_hash=input_hash,
        result=output.result,
        created_at=execution_time,
    )
    try:
        with session.begin_nested():
            session.add(evaluation)
            session.flush()
            session.add_all(
                [
                    PolicyEvaluationReason(
                        policy_evaluation_id=evaluation_id,
                        position=position,
                        reason_code=reason,
                    )
                    for position, reason in enumerate(output.reason_codes)
                ]
            )
            session.flush()
    except IntegrityError:
        existing = session.get(PolicyEvaluation, evaluation_id)
        if existing is None:
            raise
        _validate_existing_policy(session, existing, input_hash=input_hash, output=output)
        return existing
    return evaluation


def materialize_snapshot_disposition(
    session: Session,
    state_snapshot_id: UUID,
    *,
    evaluated_at: datetime | None = None,
) -> tuple[DecisionEvaluation, PolicyEvaluation]:
    """Materialize the Decision/Policy pair for one explicit snapshot; never compute state."""

    decision = materialize_decision_evaluation(
        session,
        state_snapshot_id,
        evaluated_at=evaluated_at,
    )
    policy = materialize_policy_evaluation(
        session,
        decision.decision_evaluation_id,
        evaluated_at=evaluated_at,
    )
    return decision, policy


def materialize_snapshot_dispositions(
    session: Session,
    state_snapshot_ids: Sequence[UUID],
    *,
    evaluated_at: datetime | None = None,
) -> list[tuple[DecisionEvaluation, PolicyEvaluation]]:
    """Materialize M1C only for the explicit snapshot IDs supplied by the caller."""

    return [
        materialize_snapshot_disposition(session, snapshot_id, evaluated_at=evaluated_at)
        for snapshot_id in state_snapshot_ids
    ]
